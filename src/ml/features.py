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
        Flat feature dict. All values are finite floats. NaN values are replaced
        with 0.0 so the estimator always receives a complete input vector.
        Features with domain-specific neutral defaults (e.g. bar_portion → 0.5)
        pre-fill before this pass and are preserved because they are finite.
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
    """
    Short-horizon features derived from recent candles and a live order book snapshot.

    Features:
        short_return:          Simple return over the short window: close[-1]/close[0] - 1.
        short_volatility:      Std dev of per-candle returns over the window.
        order_book_imbalance:  Signed bid/ask depth ratio at top 5 levels. Range [-1, 1].
        spread_bps:            Current live bid-ask spread in basis points.
        trade_flow_skew:       Mean taker-buy fraction minus 0.5 (requires taker_buy_volume
                               column; 0.0 if unavailable).
        volume_acceleration:   Last candle volume relative to the window mean minus 1.
        bar_portion:           Mean of (close - low) / (high - low) over the window.
                               Near 1.0 = price closed near high (bullish pressure).
                               Near 0.0 = price closed near low (bearish pressure).
                               Fallback 0.5 (neutral). No order book data required.
                               Source: Stoikov et al. (2024), SSRN 5066176.
        spread_timing:         current_spread_bps / rolling_mean_candle_range_bps - 1.
                               Negative = spread is tighter than its recent norm, which
                               makes order flow signals more reliable and persistent.
                               rolling_mean is approximated from candle high-low ranges
                               (the only intracandle spread proxy available from OHLCV).
                               IC increases over time when this is negative (Delphi Alpha,
                               Jan 2026), unlike every other signal.
    """
    recent = candles.iloc[-window:]
    close = recent["close"]
    high = recent["high"]
    low = recent["low"]
    volume = recent["volume"]

    buy_volume = recent.get("taker_buy_volume", pd.Series(dtype=float))
    total_volume = volume.replace(0, np.nan)

    trade_flow_skew = (
        (buy_volume / total_volume - 0.5).mean()
        if not buy_volume.empty
        else 0.0
    )

    # Bar portion: where did the close land within the candle's range?
    # NaN-safe: candles where high == low are excluded from the mean.
    candle_range = (high - low).replace(0, float("nan"))
    bp_mean = ((close - low) / candle_range).mean()
    bar_portion = float(bp_mean) if np.isfinite(bp_mean) else 0.5

    # Spread timing: current live spread vs the rolling mean of candle ranges.
    # The candle high-low range in bps is the best available proxy for the
    # typical bid-ask spread over each candle period when no book history exists.
    current_spread_bps = (
        (order_book.best_ask - order_book.best_bid) / order_book.mid_price * 1e4
    )
    mid_approx = ((high + low) / 2).replace(0, float("nan"))
    rolling_mean_range_bps = float(((high - low) / mid_approx * 1e4).mean())
    spread_timing = (
        current_spread_bps / rolling_mean_range_bps - 1.0
        if rolling_mean_range_bps > 0
        else 0.0
    )

    return {
        "short_return": (close.iloc[-1] / close.iloc[0] - 1) if len(close) > 1 else 0.0,
        "short_volatility": close.pct_change().std(),
        "order_book_imbalance": order_book.depth_imbalance(levels=5),
        "spread_bps": current_spread_bps,
        "trade_flow_skew": float(trade_flow_skew),
        "volume_acceleration": (
            volume.iloc[-1] / volume.iloc[:-1].mean() - 1
            if volume.iloc[:-1].mean() > 0
            else 0.0
        ),
        "bar_portion": bar_portion,
        "spread_timing": float(spread_timing),
    }


def _medium_features(candles: pd.DataFrame, window: int) -> dict[str, float]:
    """
    Medium-horizon features (minutes to ~1 hour).

    Features:
        medium_vwap_deviation:    Current price minus VWAP, normalized by VWAP.
        medium_momentum_quarter:  Return over the last window/4 candles.
        medium_momentum_half:     Return over the last window/2 candles.
        medium_momentum_full:     Return over the full medium window.
        medium_volatility:        Std dev of per-candle returns over the window.
        medium_volume_trend:      Recent quarter-window mean volume vs full-window
                                  mean volume minus 1. Positive = volume picking up.
    """
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
    """
    Long-horizon features (hours to ~1 day).

    These are contextual features. They tell the model whether the current
    microstructure noise is occurring inside a sustained trend (weight signals
    more heavily) or a ranging market (expect mean reversion). They do not
    directly predict short-horizon drift — they condition the other features.

    Features:
        long_trend_return:  Total return over the long window.
        long_trend_slope:   Linear regression slope normalized by mean price.
                            Positive = sustained uptrend, negative = downtrend.
        long_above_sma:     1.0 if current price is above the long-window SMA,
                            0.0 otherwise.
    """
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
