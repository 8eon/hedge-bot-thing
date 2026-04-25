"""
Avellaneda-Stoikov market making controller for Hummingbot V2.

This controller bridges the pure-math A-S model in src/core/ with Hummingbot's
order management and data feed systems. Its responsibilities:

  1. Pull candle data and the live order book from the Market Data Provider.
  2. Compute multi-scale features and request drift/regime estimates from the ML layer.
  3. Call the A-S model to get optimal bid/ask prices.
  4. Translate those prices into Hummingbot ExecutorConfig objects.
  5. Hand off any fills to the TradeLogger.

The controller itself contains no mathematical logic. If you need to understand
the quote calculation, read src/core/avellaneda_stoikov.py.

Configuration is defined in AvellanedaStoikovConfig and loaded from YAML by
Hummingbot's --v2 startup path.
"""

from __future__ import annotations

import logging
import sys
import time
from decimal import Decimal
from pathlib import Path
from typing import Optional

import numpy as np

# Allow imports from src/ when running inside Hummingbot's working directory.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.core.avellaneda_stoikov import (
    MarketState,
    ModelParameters,
    QuoteResult,
    compute_quotes,
    inventory_is_at_limit,
)
from src.ml.drift_estimator import DriftEstimator
from src.ml.features import OrderBookSnapshot, compute_features
from src.ml.regime_classifier import MarketRegime, RegimeClassifier
from src.tax.trade_logger import TradeSide, TradeLogger, TradeRecord

try:
    from pydantic import Field
    from hummingbot.strategy_v2.controllers.controller_base import (
        ControllerBase,
        ControllerConfigBase,
    )
    from hummingbot.strategy_v2.executors.position_executor.data_types import (
        PositionExecutorConfig,
    )
    from hummingbot.strategy_v2.models.executor_actions import (
        CreateExecutorAction,
        ExecutorAction,
        StopExecutorAction,
    )
    HUMMINGBOT_AVAILABLE = True
except ImportError:
    # Allow the module to be imported in tests without a full Hummingbot install.
    HUMMINGBOT_AVAILABLE = False
    ControllerBase = object
    ControllerConfigBase = object


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

if HUMMINGBOT_AVAILABLE:
    from hummingbot.client.config.config_data_types import ClientFieldData

    class AvellanedaStoikovConfig(ControllerConfigBase):
        """
        YAML-configurable parameters for the A-S controller.
        All numeric parameters can be updated live without restarting.
        """
        controller_name: str = "avellaneda_stoikov_controller"

        exchange: str = Field(
            default="binance_paper_trade",
            client_data=ClientFieldData(
                prompt_on_new=True,
                prompt=lambda mi: "Exchange connector (e.g. binance_paper_trade): ",
            ),
        )
        trading_pair: str = Field(
            default="BTC-USDT",
            client_data=ClientFieldData(
                prompt_on_new=True,
                prompt=lambda mi: "Trading pair (e.g. BTC-USDT): ",
            ),
        )
        order_amount_quote: Decimal = Field(
            default=Decimal("50"),
            client_data=ClientFieldData(
                is_updatable=True,
                prompt_on_new=True,
                prompt=lambda mi: "Order size in quote asset (e.g. 50 USDT): ",
            ),
        )

        # Avellaneda-Stoikov model parameters
        gamma: float = Field(
            default=0.1,
            gt=0,
            client_data=ClientFieldData(
                is_updatable=True,
                prompt_on_new=True,
                prompt=lambda mi: "Risk-aversion gamma (e.g. 0.1): ",
            ),
        )
        kappa: float = Field(
            default=1.5,
            gt=0,
            client_data=ClientFieldData(
                is_updatable=True,
                prompt_on_new=True,
                prompt=lambda mi: "Order arrival intensity kappa (e.g. 1.5): ",
            ),
        )
        time_horizon_seconds: float = Field(
            default=3600.0,
            gt=0,
            client_data=ClientFieldData(
                is_updatable=True,
                prompt_on_new=False,
                prompt=lambda mi: "Trading session length in seconds (e.g. 3600): ",
            ),
        )
        max_inventory_base: float = Field(
            default=0.01,
            gt=0,
            client_data=ClientFieldData(
                is_updatable=True,
                prompt_on_new=True,
                prompt=lambda mi: "Max inventory in base asset (e.g. 0.01 BTC): ",
            ),
        )

        # High-volatility regime spread multiplier
        high_vol_spread_multiplier: float = Field(
            default=3.0,
            gt=1.0,
            client_data=ClientFieldData(
                is_updatable=True,
                prompt_on_new=False,
                prompt=lambda mi: "Spread multiplier during high-volatility regime: ",
            ),
        )

        # Candle feed configuration (matches StrategyV2ConfigBase format)
        candle_interval: str = Field(default="1m")
        candle_max_records: int = Field(default=1500)  # ~25 hours of 1m candles

        # Trade log path
        trade_log_path: str = Field(default="logs/trades.jsonl")


# ---------------------------------------------------------------------------
# Controller
# ---------------------------------------------------------------------------

class AvellanedaStoikovController(ControllerBase if HUMMINGBOT_AVAILABLE else object):
    """
    Hummingbot V2 controller implementing A-S market making with ML-assisted
    drift estimation and regime detection.

    Each tick:
      1. Fetch current candles and order book.
      2. Compute features → get drift estimate + regime label.
      3. Compute optimal quotes via A-S model.
      4. If quotes changed materially, cancel old executors and create new ones.
      5. Log any completed fills to the trade logger.
    """

    def __init__(self, config: "AvellanedaStoikovConfig", *args, **kwargs) -> None:
        super().__init__(config, *args, **kwargs)
        self.config = config

        self._params = ModelParameters(
            gamma=config.gamma,
            kappa=config.kappa,
            time_horizon=config.time_horizon_seconds,
            max_inventory=config.max_inventory_base,
        )
        self._session_start: float = time.time()

        self._drift_estimator = DriftEstimator()
        self._regime_classifier = RegimeClassifier()
        self._trade_logger = TradeLogger(Path(config.trade_log_path))

        # Last computed quotes — used to avoid redundant order cancellations.
        self._last_quotes: Optional[QuoteResult] = None

    def _refresh_params(self) -> None:
        """Rebuild ModelParameters from config. Called each tick to pick up live updates."""
        self._params = ModelParameters(
            gamma=self.config.gamma,
            kappa=self.config.kappa,
            time_horizon=self.config.time_horizon_seconds,
            max_inventory=self.config.max_inventory_base,
        )

    def _get_market_state(self, drift: float, volatility: float, mid_price: float) -> MarketState:
        inventory = self._get_inventory_base()
        elapsed = time.time() - self._session_start
        return MarketState(
            mid_price=mid_price,
            volatility=volatility,
            inventory=inventory,
            elapsed=elapsed,
            drift=drift,
        )

    def _get_inventory_base(self) -> float:
        """Return current base asset holdings from the connector."""
        try:
            connector = self.market_data_provider.get_connector(self.config.exchange)
            base_asset = self.config.trading_pair.split("-")[0]
            balance = connector.get_available_balance(base_asset)
            return float(balance)
        except Exception as e:
            self.logger().warning(
                f"Could not fetch {self.config.trading_pair.split('-')[0]} balance, "
                f"using 0.0 — inventory limits may not be accurate: {e}"
            )
            return 0.0

    def _compute_volatility(self, candles) -> float:
        """Estimate per-second volatility from recent candle close prices."""
        closes = candles["close"].values.astype(float)
        if len(closes) < 2:
            return 0.001  # safe fallback

        log_returns = np.diff(np.log(closes))
        # Convert from per-candle to per-second using candle interval.
        candle_seconds = _interval_to_seconds(self.config.candle_interval)
        per_candle_vol = float(np.std(log_returns))
        return per_candle_vol / (candle_seconds ** 0.5)

    def determine_executor_actions(self) -> list["ExecutorAction"]:
        """
        Main entry point called by Hummingbot on each strategy tick.
        Returns a list of executor actions (create / stop).

        TODO: Before creating new orders, active executors from the previous tick
        must be stopped. Without this, each tick accumulates more open orders.
        Implement by calling StopExecutorAction for all active executor IDs tracked
        in self.executors_info before appending CreateExecutorActions. This requires
        verifying the exact executor lifecycle API against the installed Hummingbot
        version before implementing, to avoid cancelling fills mid-execution.
        """
        self._refresh_params()

        try:
            candles_df = self.market_data_provider.get_candles_df(
                connector_name=self.config.exchange,
                trading_pair=self.config.trading_pair,
                interval=self.config.candle_interval,
                max_records=self.config.candle_max_records,
            )
            order_book_raw = self.market_data_provider.get_order_book(
                connector_name=self.config.exchange,
                trading_pair=self.config.trading_pair,
            )
        except Exception as e:
            self.logger().warning(f"Data fetch failed, skipping tick: {e}")
            return []

        order_book = _parse_order_book(order_book_raw)
        mid_price = order_book.mid_price
        volatility = self._compute_volatility(candles_df)

        features = compute_features(candles_df, order_book)
        drift = self._drift_estimator.predict(features)
        regime = self._regime_classifier.predict(features)

        state = self._get_market_state(drift, volatility, mid_price)
        quotes = compute_quotes(self._params, state)

        if regime == MarketRegime.HIGH_VOLATILITY:
            half_spread = quotes.spread / 2 * self.config.high_vol_spread_multiplier
            quotes = QuoteResult(
                bid=quotes.reservation_price - half_spread,
                ask=quotes.reservation_price + half_spread,
                reservation_price=quotes.reservation_price,
                spread=half_spread * 2,
                time_remaining=quotes.time_remaining,
                inventory_skew=quotes.inventory_skew,
            )

        self._last_quotes = quotes
        return self._build_executor_actions(quotes, state.inventory, regime)

    def _build_executor_actions(
        self,
        quotes: "QuoteResult",
        inventory: float,
        regime: MarketRegime,
    ) -> list["ExecutorAction"]:
        actions: list["ExecutorAction"] = []

        place_bid = not inventory_is_at_limit(inventory, self._params, "buy")
        place_ask = not inventory_is_at_limit(inventory, self._params, "sell")

        # In a strongly trending regime, halve order size to reduce adverse exposure.
        amount_multiplier = 0.5 if regime == MarketRegime.TRENDING else 1.0
        order_amount = float(self.config.order_amount_quote) * amount_multiplier / quotes.bid

        if place_bid:
            actions.append(self._make_limit_order("buy", quotes.bid, order_amount))
        if place_ask:
            actions.append(self._make_limit_order("sell", quotes.ask, order_amount))

        return actions

    def _make_limit_order(
        self, side: str, price: float, amount: float
    ) -> "CreateExecutorAction":
        from hummingbot.core.data_type.common import TradeType
        from hummingbot.strategy_v2.executors.position_executor.data_types import (
            PositionExecutorConfig,
        )
        from hummingbot.strategy_v2.models.executor_actions import CreateExecutorAction

        trade_type = TradeType.BUY if side == "buy" else TradeType.SELL
        config = PositionExecutorConfig(
            timestamp=time.time(),
            connector_name=self.config.exchange,
            trading_pair=self.config.trading_pair,
            side=trade_type,
            entry_price=Decimal(str(round(price, 8))),
            amount=Decimal(str(round(amount, 8))),
        )
        return CreateExecutorAction(executor_config=config, controller_id=self.config.id)

    def on_order_filled(self, fill_event) -> None:
        """
        Called by Hummingbot when an order fills. Records the trade to the log.
        Override point for fill handling.
        """
        quote_asset = self.config.trading_pair.split("-")[1]
        fee, fee_asset = _extract_fee(fill_event.trade_fee, quote_asset)

        record = TradeRecord(
            trade_id=fill_event.exchange_trade_id,
            timestamp=TradeRecord.now_utc(),
            exchange=self.config.exchange,
            trading_pair=self.config.trading_pair,
            side=TradeSide.BUY if fill_event.trade_type.name == "BUY" else TradeSide.SELL,
            base_asset=self.config.trading_pair.split("-")[0],
            quote_asset=quote_asset,
            quantity=float(fill_event.amount),
            price=float(fill_event.price),
            fee=fee,
            fee_asset=fee_asset,
            order_id=fill_event.order_id,
            is_paper="paper" in self.config.exchange.lower(),
        )
        self._trade_logger.record(record)

    def to_format_status(self) -> list[str]:
        """Status lines shown by Hummingbot's `status` command."""
        lines = [f"Strategy: Avellaneda-Stoikov  |  Pair: {self.config.trading_pair}"]
        if self._last_quotes:
            q = self._last_quotes
            lines.append(
                f"  Bid: {q.bid:.4f}  |  Ask: {q.ask:.4f}  |  "
                f"Spread: {q.spread:.4f}  |  Reservation: {q.reservation_price:.4f}"
            )
            lines.append(
                f"  Inventory skew: {q.inventory_skew:.6f}  |  "
                f"Time remaining: {q.time_remaining:.2%}"
            )
        return lines


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _extract_fee(trade_fee, quote_asset: str) -> tuple[float, str]:
    """
    Extract fee amount and asset from a Hummingbot TradeFee object.

    Hummingbot represents fees in two ways:
      - flat_fees: a list of (token, amount) pairs for fixed fees
      - percent / percent_token: a percentage of trade value in a specific token

    We prefer flat_fees when present, as they are exact. The percentage form
    is an approximation since we don't have the exact fill price here.
    """
    if hasattr(trade_fee, "flat_fees") and trade_fee.flat_fees:
        # Sum all flat fee amounts denominated in the same token.
        # For mixed-token fees (rare), take the first entry only.
        token = trade_fee.flat_fees[0].token
        amount = sum(f.amount for f in trade_fee.flat_fees if f.token == token)
        return float(amount), token

    if hasattr(trade_fee, "percent") and trade_fee.percent:
        # Percentage fee: amount is unknowable here without the fill value.
        # Store the raw percent and token so downstream tax code can resolve it.
        token = getattr(trade_fee, "percent_token", None) or quote_asset
        return float(trade_fee.percent), token

    return 0.0, quote_asset


def _parse_order_book(raw) -> OrderBookSnapshot:
    """Convert Hummingbot's order book object to our OrderBookSnapshot."""
    bids = [(float(p), float(s)) for p, s in raw.bid_entries()]
    asks = [(float(p), float(s)) for p, s in raw.ask_entries()]
    return OrderBookSnapshot(
        bid_prices=[b[0] for b in bids],
        bid_sizes=[b[1] for b in bids],
        ask_prices=[a[0] for a in asks],
        ask_sizes=[a[1] for a in asks],
    )


def _interval_to_seconds(interval: str) -> float:
    """Convert a candle interval string (e.g. '1m', '5m', '1h') to seconds."""
    units = {"s": 1, "m": 60, "h": 3600, "d": 86400}
    unit = interval[-1]
    if unit not in units:
        raise ValueError(
            f"Unrecognized candle interval unit '{unit}' in '{interval}'. "
            f"Expected one of: {list(units.keys())}"
        )
    value = float(interval[:-1])
    return value * units[unit]
