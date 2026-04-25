"""
Avellaneda-Stoikov market making model.

Reference: Avellaneda, M. & Stoikov, S. (2008). "High-frequency trading in a limit order book."
Quantitative Finance, 8(3), 217-224.

The model solves for optimal bid/ask placement for a dealer who wants to maximize expected
utility of terminal wealth while managing inventory risk. Two key outputs:

  Reservation price:  r = s + μ·(T-t) - q·γ·σ²·(T-t)
  Optimal spread:     δ = γ·σ²·(T-t) + (2/γ)·ln(1 + γ/κ)

where:
  s   = current mid price
  μ   = expected short-horizon drift (provided by ML estimator; 0 if not available)
  q   = current inventory in units of base asset (positive = long, negative = short)
  γ   = risk-aversion parameter (higher → wider spreads, more aggressive inventory skewing)
  σ   = volatility of the asset (per unit time, matching the time horizon units)
  T-t = remaining time in the trading session (normalized to [0, 1])
  κ   = order arrival rate intensity (higher → tighter spreads)

All prices are in quote asset units (e.g. USDT).
"""

import math
from dataclasses import dataclass


@dataclass(frozen=True)
class ModelParameters:
    """
    Static configuration for the Avellaneda-Stoikov model.

    Attributes:
        gamma:        Risk-aversion coefficient. Controls the trade-off between
                      spread revenue and inventory risk. Typical range: 0.01 – 0.5.
        kappa:        Order arrival intensity. Higher values indicate a more liquid
                      market with faster order flow, resulting in tighter optimal spreads.
                      Typical range: 0.5 – 5.0.
        time_horizon: Session length in seconds. The model spreads inventory risk
                      over this window. A shorter horizon causes more aggressive
                      spread widening as q grows.
        max_inventory: Hard cap on absolute inventory in base asset units. Orders
                       that would breach this limit are not placed.
    """
    gamma: float
    kappa: float
    time_horizon: float  # seconds
    max_inventory: float

    def __post_init__(self) -> None:
        if self.gamma <= 0:
            raise ValueError(f"gamma must be positive, got {self.gamma}")
        if self.kappa <= 0:
            raise ValueError(f"kappa must be positive, got {self.kappa}")
        if self.time_horizon <= 0:
            raise ValueError(f"time_horizon must be positive, got {self.time_horizon}")
        if self.max_inventory <= 0:
            raise ValueError(f"max_inventory must be positive, got {self.max_inventory}")


@dataclass(frozen=True)
class MarketState:
    """
    Snapshot of market conditions required for a single quote calculation.

    Attributes:
        mid_price:   Current mid price of the trading pair (quote asset).
        volatility:  Estimated volatility per second (annualized σ / sqrt(seconds_per_year)).
        inventory:   Current holdings in base asset units. Positive = long, negative = short.
        elapsed:     Seconds elapsed since the start of the current trading session.
        drift:       Short-horizon drift estimate from the ML layer (quote asset per second).
                     Defaults to 0.0, which replicates the original A-S assumption.
    """
    mid_price: float
    volatility: float
    inventory: float
    elapsed: float
    drift: float = 0.0

    def __post_init__(self) -> None:
        if self.mid_price <= 0:
            raise ValueError(f"mid_price must be positive, got {self.mid_price}")
        if self.volatility < 0:
            raise ValueError(f"volatility must be non-negative, got {self.volatility}")
        if self.elapsed < 0:
            raise ValueError(f"elapsed must be non-negative, got {self.elapsed}")


@dataclass(frozen=True)
class QuoteResult:
    """
    Output of a single model evaluation.

    Attributes:
        bid:              Optimal bid price to post.
        ask:              Optimal ask price to post.
        reservation_price: The risk-adjusted mid price the model centers quotes around.
        spread:           Total optimal spread (ask - bid).
        time_remaining:   Normalized remaining time used in this calculation (0–1).
        inventory_skew:   Signed shift applied to reservation price from inventory.
                          Positive = model shifted quotes up (short inventory).
    """
    bid: float
    ask: float
    reservation_price: float
    spread: float
    time_remaining: float
    inventory_skew: float

    @property
    def mid(self) -> float:
        return (self.bid + self.ask) / 2


def compute_quotes(params: ModelParameters, state: MarketState) -> QuoteResult:
    """
    Compute optimal bid and ask prices given model parameters and current market state.

    Returns a QuoteResult. If the remaining session time is zero (end of session),
    spreads are widened to their maximum to discourage further fills.

    This function is pure: it has no side effects and depends only on its arguments.
    It can be called freely in tests, backtests, or live trading.
    """
    time_remaining = max(0.0, 1.0 - state.elapsed / params.time_horizon)

    # At session end, widen to a very large spread to stop quoting gracefully.
    if time_remaining == 0.0:
        half_spread = state.mid_price  # effectively no fills possible
        r = state.mid_price
        return QuoteResult(
            bid=r - half_spread,
            ask=r + half_spread,
            reservation_price=r,
            spread=2 * half_spread,
            time_remaining=0.0,
            inventory_skew=0.0,
        )

    # T-t in actual seconds: volatility is per-second, so the variance term must
    # use real elapsed time, not the normalized [0, 1] ratio.
    seconds_remaining = time_remaining * params.time_horizon
    variance_term = params.gamma * (state.volatility ** 2) * seconds_remaining

    # Inventory skew: shifts reservation price away from current mid to encourage
    # rebalancing. A long inventory (q > 0) pulls quotes down; short pulls up.
    inventory_skew = state.inventory * variance_term

    # Drift contribution: ML-supplied drift (price/second) × seconds remaining.
    drift_contribution = state.drift * seconds_remaining

    reservation_price = state.mid_price + drift_contribution - inventory_skew

    # Optimal half-spread from the A-S closed-form solution.
    # The log term penalizes tight spreads relative to order arrival intensity.
    spread = variance_term + (2.0 / params.gamma) * math.log(1.0 + params.gamma / params.kappa)
    half_spread = spread / 2.0

    bid = reservation_price - half_spread
    ask = reservation_price + half_spread

    return QuoteResult(
        bid=bid,
        ask=ask,
        reservation_price=reservation_price,
        spread=spread,
        time_remaining=time_remaining,
        inventory_skew=inventory_skew,
    )


def inventory_is_at_limit(inventory: float, params: ModelParameters, side: str) -> bool:
    """
    Return True if placing an order on the given side would breach the inventory cap.

    side must be 'buy' or 'sell'.
    """
    if side == "buy" and inventory >= params.max_inventory:
        return True
    if side == "sell" and inventory <= -params.max_inventory:
        return True
    return False
