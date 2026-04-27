# hedge-bot-thing

A (WIP) professional-grade cryptocurrency market making system built on [Hummingbot](https://hummingbot.org/), implementing the Avellaneda-Stoikov model with machine learning-assisted parameter estimation and automated IRS tax reporting.

---

## Table of Contents

- [Overview](#overview)
- [Architecture](#architecture)
- [Strategy](#strategy)
- [Machine Learning](#machine-learning)
- [Tax Reporting](#tax-reporting)
- [Roadmap](#roadmap)
- [License](#license)

---

## Overview

This project applies quantitative market making techniques — standard practice in institutional trading — to cryptocurrency markets using an open source foundation. Rather than speculating on price direction, the system profits by continuously quoting bid and ask prices around the market mid-price and capturing the spread, managing inventory risk dynamically through the Avellaneda-Stoikov framework.

The approach is notable for several reasons:

- **Direction-neutral profitability.** Returns are generated from spread capture as opposed to price prediction, making performance consistent across bull and bear market conditions.
- **Principled risk management.** Inventory exposure is controlled mathematically rather than through ad hoc rules.
- **ML as a precision tool for parameter estimation** Machine learning is scoped to estimating specific model parameters — short-term drift and market regime — rather than making unconstrained trading decisions.

---

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│                      Exchange Layer                      │
│         CEX via Hummingbot connectors (REST/WS)          │
└───────────────────────┬─────────────────────────────────┘
                        │
┌───────────────────────▼─────────────────────────────────┐
│                    Strategy Layer                        │
│            Avellaneda-Stoikov Market Making              │
│      Inventory skewing · Dynamic spread · Risk param     │
└──────────┬────────────────────────────┬─────────────────┘
           │                            │
┌──────────▼──────────┐    ┌────────────▼────────────────┐
│      ML Layer       │    │        Trade Logger          │
│  Drift estimator    │    │  Timestamped execution log   │
│  Regime classifier  │    │  Cost basis tracking         │
└─────────────────────┘    └────────────┬────────────────┘
                                        │
                           ┌────────────▼────────────────┐
                           │      Tax Reporting           │
                           │  Form 8949 / Schedule D      │
                           │  FIFO · HIFO · LIFO          │
                           └─────────────────────────────┘
```

---

## Strategy

The core trading strategy is the **Avellaneda-Stoikov market making model**, which solves the optimal quote placement problem for a dealer operating in a limit order book.

The model derives a *reservation price* — the price at which a risk-neutral market maker is indifferent between buying and selling — based on the current mid-price, inventory position, time horizon, and risk-aversion parameter. Bid and ask quotes are then placed symmetrically around this reservation price at a spread derived from market volatility and order arrival rates.

The key properties that make this preferable to a fixed-spread approach:

- **Inventory awareness.** As inventory skews in one direction, quotes are automatically shifted to encourage rebalancing trades and limit further exposure.
- **Volatility-responsive spreads.** Spreads widen in high-volatility conditions to compensate for increased adverse selection risk.
- **Mathematically grounded.** The model is derived from first principles (stochastic optimal control), so behavior is predictable and auditable.

---

## Machine Learning

ML is used to estimate two parameters that the base model cannot derive from the order book alone:

### Short-Term Drift Estimation

The Avellaneda-Stoikov reservation price includes a drift term representing the expected short-horizon price movement. The base model assumes zero drift, which is conservative but leaves performance on the table in trending conditions.

A regression model is trained to predict short-horizon drift (seconds to minutes) using features drawn from multiple time scales. The distinction between feature lookback window and prediction horizon is intentional: longer-lookback features provide broader market context that informs the short-term estimate, without introducing a horizon mismatch between the model's output and the trading time frame.

**Short-horizon features** (seconds to low minutes):
- Order book depth imbalance
- Recent trade flow directional skew
- Bid/ask volume asymmetry

**Medium-horizon features** (minutes to hours):
- Price momentum over 5, 15, and 60-minute windows
- Volume-weighted average price (VWAP) deviation
- Rolling volatility regime

**Long-horizon features** (hours to days):
- Multi-day trend direction and strength
- Sustained order flow bias
- Broader market context (e.g. correlation with BTC if trading an alt)

The longer-horizon features act as contextual inputs — they tell the model whether the short-term noise is occurring inside a sustained trend or a ranging market, which substantially improves estimation accuracy. The output is still a short-horizon drift scalar fed directly into the reservation price calculation.

This signal shifts the reservation price in the direction of predicted flow, reducing adverse selection during trending periods.

### Market Regime Classification

A classifier identifies the current market regime — ranging, trending, or high-volatility — and adjusts strategy behavior accordingly:

| Regime | Action |
|---|---|
| Ranging | Standard Avellaneda-Stoikov parameters |
| Trending | Aggressive quote skewing; reduced order size |
| High-volatility | Spread widening; potential quoting suspension |

This helps to prevent the strategy from operating in conditions where market making is structurally unprofitable.

---

## Tax Reporting

Every executed trade is logged with full metadata required for tax purposes: timestamp, trading pair, side, quantity, executed price, fee, and exchange. From this log, the system produces:

- **Cost basis tracking** using FIFO (default), HIFO, or LIFO accounting methods
- **Form 8949-compatible output** listing each disposal with acquisition date, disposal date, proceeds, and cost basis
- **Schedule D summary** of short-term and long-term capital gains/losses

All tax computation is performed locally using open source libraries. 

---

## Roadmap

| Phase | Description |
|---|---|---|
| 1 | Hummingbot setup, paper trading, CEX testnet connectivity, trade logging | 
| 2 | Avellaneda-Stoikov strategy implementation |
| 3 | Tax pipeline: cost basis accounting and Form 8949 export |
| 4 | ML drift estimator and regime classifier |
| 5 | Backtesting framework and historical validation |
| 6 | Live deployment with position limits and kill switches |

---

## License

Apache 2.0 — see [LICENSE](LICENSE).
