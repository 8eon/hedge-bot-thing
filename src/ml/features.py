"""
Multi-scale feature engineering for the drift estimator and regime classifier.

Features are grouped into three time-scale buckets, as described in the README:

  Short  (seconds – low minutes): microstructure signals, order book state
  Medium (minutes – hours):       momentum, VWAP deviation, rolling volatility
  Long   (hours – days):          trend direction/strength, sustained flow bias

The primary input is a pandas DataFrame of OHLCV candles plus an order book
snapshot. All features are returned as a single flat dict keyed by feature name,
suitable for feeding directly into scikit-learn estimators.

This module is intentionally framework-agnostic: it takes plain data structures
and returns plain data structures. The Hummingbot controller is responsible for
fetching raw data and calling into this module.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import numpy as np
import pandas as pd


@dataclass
class OrderBookSnapshot:
    """
    Top-of-book and depth data at the moment of feature computation.

    bid_prices / ask_prices: price levels, index 0 = best
    bid_sizes  / ask_sizes:  quantity at each price level
    """
    bid_prices: list[float]
    bid_sizes: list[float]
    ask_prices: list[float]
    ask_sizes: list[float]

    @property
    def best_bid(self) -> float:
        return self.bid_prices[0]

    @property
    def best_ask(self) -> float:
        return self.ask_prices[0]

    @property
    def mid_price(self) -> float:
        return (self.best_bid + self.best_ask) / 2

    def depth_imbalance(self, levels: int = 5) -> float:
        """
        Signed order book imbalance over the top `levels` levels.
        Range: [-1, 1]. Positive = more bid pressure, negative = more ask pressure.
        """
        bid_vol = sum(self.bid_sizes[:levels])
        ask_vol = sum(self.ask_sizes[:levels])
        total = bid_vol + ask_vol
        if total == 0:
            return 0.0
        return (bid_vol - ask_vol) / total


def compute_features(
    candles: pd.DataFrame,
    order_book: OrderBookSnapshot,
    short_window: int = 5,
    medium_window: int = 60,
    long_window: int = 1440,
) -> dict[str, float]:
    """
    Compute the full multi-scale feature vector from candle history and a live
    order book snapshot.

    Parameters
    ----------
    candles:
        OHLCV DataFrame indexed by timestamp, sorted ascending.
        Required columns: open, high, low, close, volume.
        Candle interval should be consistent (e.g. all 1-minute candles).
    order_book:
        Current order book snapshot for microstructure features.
    short_window:
        Number of candles for short-horizon features.
    medium_window:
        Number of candles for medium-horizon features.
    long_window:
        Number of candles for long-horizon features.

    Returns
    -------
    dict[str, float]
        Flat feature dict. All values are finite floats. NaN values are filled
        with 0.0 so the estimator always receives a complete input vector.
    """
    features: dict[str, float] = {}

    features.update(_short_features(candles, order_book, short_window))
    features.update(_medium_features(candles, medium_window))
    features.update(_long_features(candles, long_window))

    # Replace any NaN that slipped through (e.g. insufficient history) with 0.
    return {k: float(v) if np.isfinite(v) else 0.0 for k, v in features.items()}


def _short_features(
    candles: pd.DataFrame,
    order_book: OrderBookSnapshot,
    window: int,
) -> dict[str, float]:
    recent = candles.iloc[-window:]
    close = recent["close"]
    volume = recent["volume"]

    buy_volume = recent.get("taker_buy_volume", pd.Series(dtype=float))
    total_volume = volume.replace(0, np.nan)

    trade_flow_skew = (
        (buy_volume / total_volume - 0.5).mean()
        if not buy_volume.empty
        else 0.0
    )

    return {
        "short_return": (close.iloc[-1] / close.iloc[0] - 1) if len(close) > 1 else 0.0,
        "short_volatility": close.pct_change().std(),
        "order_book_imbalance": order_book.depth_imbalance(levels=5),
        "spread_bps": (order_book.best_ask - order_book.best_bid) / order_book.mid_price * 1e4,
        "trade_flow_skew": float(trade_flow_skew),
        "volume_acceleration": (
            volume.iloc[-1] / volume.iloc[:-1].mean() - 1
            if volume.iloc[:-1].mean() > 0
            else 0.0
        ),
    }


def _medium_features(candles: pd.DataFrame, window: int) -> dict[str, float]:
    recent = candles.iloc[-window:]
    close = recent["close"]
    volume = recent["volume"]

    vwap = (close * volume).sum() / volume.sum() if volume.sum() > 0 else close.mean()
    current_price = close.iloc[-1]

    # Momentum at 1/4, 1/2, and full medium window
    w4 = window // 4
    w2 = window // 2
    mom_quarter = close.iloc[-1] / close.iloc[-w4] - 1 if len(close) >= w4 else 0.0
    mom_half = close.iloc[-1] / close.iloc[-w2] - 1 if len(close) >= w2 else 0.0
    mom_full = close.iloc[-1] / close.iloc[0] - 1 if len(close) >= 2 else 0.0

    return {
        "medium_vwap_deviation": (current_price - vwap) / vwap if vwap > 0 else 0.0,
        "medium_momentum_quarter": float(mom_quarter),
        "medium_momentum_half": float(mom_half),
        "medium_momentum_full": float(mom_full),
        "medium_volatility": close.pct_change().std(),
        "medium_volume_trend": (
            volume.iloc[-window // 4 :].mean() / volume.mean() - 1
            if volume.mean() > 0
            else 0.0
        ),
    }


def _long_features(candles: pd.DataFrame, window: int) -> dict[str, float]:
    recent = candles.iloc[-window:]
    close = recent["close"]

    if len(close) < 2:
        return {
            "long_trend_return": 0.0,
            "long_trend_slope": 0.0,
            "long_above_sma": 0.0,
        }

    long_return = close.iloc[-1] / close.iloc[0] - 1

    # Linear regression slope as a normalized trend strength measure.
    x = np.arange(len(close), dtype=float)
    slope = float(np.polyfit(x, close.values, 1)[0]) / close.mean()

    sma = close.mean()
    above_sma = float(close.iloc[-1] > sma)

    return {
        "long_trend_return": float(long_return),
        "long_trend_slope": slope,
        "long_above_sma": above_sma,
    }
