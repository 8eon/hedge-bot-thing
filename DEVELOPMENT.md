# Development State

This file is the source of truth for session continuity. Read it fully at the start of every session before touching any code. Update it before ending a session.

---

## What this project is

An advanced cryptocurrency market making bot built on Hummingbot V2. It implements the Avellaneda-Stoikov market making model with a machine learning layer for short-horizon drift estimation and market regime detection, plus IRS-compliant trade logging.

The user has a C systems programming background. They are not a quant finance expert but learns fast. Keep explanations grounded.

---

## File map

```
src/core/avellaneda_stoikov.py   Pure A-S math. No framework deps. Fully implemented.
src/ml/features.py               Multi-scale feature engineering. Fully implemented.
src/ml/drift_estimator.py        Ridge regression drift estimator. Implemented; no trained model yet.
src/ml/regime_classifier.py      Random Forest regime classifier. Implemented; no trained model yet.
src/tax/trade_logger.py          Append-only JSONL trade log. Fully implemented.
controllers/avellaneda_stoikov_controller.py  Hummingbot V2 controller. Implemented with one known gap (see below).
scripts/hedge_bot.py             Hummingbot entry point script. Thin wrapper, implemented.
conf/scripts/conf_hedge_bot_1.yml.example  Config template. Copy to .yml to run.
```

---

## Architecture decisions (with reasoning)

**Pure math lives in `src/core/`, controller is the only Hummingbot file.**
Separating math from framework means the A-S model can be unit tested and backtested without installing Hummingbot. This was validated when a critical bug was found (see below) that would have been caught earlier by unit tests.

**ML models fall back to safe defaults when untrained.**
`DriftEstimator.predict()` returns 0.0 (zero drift), `RegimeClassifier.predict()` returns RANGING when no model file exists. The system runs correctly from day one with no ML data. This is intentional — collect paper trading data first, then train.

**Multi-scale features: long lookback windows, short prediction horizon.**
Features span seconds (microstructure) through days (trend), but the *output* of the drift estimator is always short-horizon. Long-window features are contextual inputs to a short-horizon prediction, not a horizon mismatch. This is the key design point.

**JSONL trade log is append-only.**
Immutable audit trail. Each line is self-contained for cost basis calculation. Paper trades are flagged and excluded from tax output.

**`TradeSide` is a `str` Enum.**
Serializes cleanly to JSON without a custom encoder. Important for the JSONL log.

---

## Bugs found and fixed (do not re-introduce)

**variance_term unit bug (critical):**
`variance_term` must use `seconds_remaining = time_remaining * params.time_horizon`, not just `time_remaining`. Volatility is per-second, so `σ²*(T-t)` requires actual seconds. Using the normalized [0,1] ratio made spreads ~3600x too narrow on a 1-hour session. Fixed in `avellaneda_stoikov.py`.

**`_interval_to_seconds` silent fallback:**
Previously fell back to 60s for unrecognized interval units. Now raises `ValueError`. Silently wrong > loudly wrong.

**`TrailingStop` unused import in controller:**
Removed. Was imported but never referenced.

**`from dataclasses import replace` dead code in controller:**
Was imported inside `determine_executor_actions` but not used — `QuoteResult(...)` is constructed directly. Removed.

**Fee extraction:**
Original code assumed `trade_fee.percent * amount * price`. Hummingbot's `TradeFee` can represent fees as either flat fees or percentages. Replaced with `_extract_fee()` helper that handles both forms.

---

## Known gaps (must be resolved before live trading)

**Order cancellation in `determine_executor_actions`.**
The controller creates new orders every tick but does not cancel stale ones from the previous tick. This would accumulate open orders indefinitely. A `StopExecutorAction` for each active executor must be issued before creating new ones. The correct implementation requires testing against the installed Hummingbot version to understand the executor lifecycle API — do not guess at this. See the TODO comment in `determine_executor_actions`.

**`on_order_filled` hook may not fire automatically.**
In Hummingbot V2, fill events route through the executor framework, not directly to controller methods. Verify whether `on_order_filled` on the controller is actually called, or whether fills need to be captured differently.

**`scripts/hedge_bot.py` not fully wired.**
The `HedgeBot` class inherits `StrategyV2Base` but `init_markets` is a no-op and the controller is not explicitly instantiated. This needs to be completed once Hummingbot is installed and the V2 wiring pattern is confirmed.

---

## Roadmap

| Phase | Description | Status |
|---|---|---|
| 1 | Hummingbot setup, paper trading, CEX testnet connectivity, trade logging | In progress |
| 2 | Avellaneda-Stoikov strategy — resolve order cancellation gap, verify fill hook | Pending |
| 3 | Tax pipeline: cost basis accounting (FIFO/HIFO/LIFO) and Form 8949 export | Pending |
| 4 | ML training loop: accumulate paper trading data, train drift + regime models | Pending |
| 5 | Backtesting framework and historical validation | Pending |
| 6 | Live deployment with hard position limits and kill switches | Pending |

---

## Immediate next steps

1. Write unit tests for `src/core/avellaneda_stoikov.py` — the variance_term bug was only found in review, not by tests. Tests would catch it first next time.
2. Install Hummingbot and run the controller against Binance paper trade to confirm connectivity and the executor lifecycle.
3. Resolve the order cancellation gap once the executor API is confirmed.

---

## Session log

| Date | What happened |
|---|---|
| 2026-04-25 | Initial project setup. Implemented all Phase 1 files. Code review pass found and fixed variance_term bug, unused imports, silent exception in inventory fetch, fee extraction, wrong pyproject.toml build backend, scipy removed. Order cancellation gap identified and documented. |
