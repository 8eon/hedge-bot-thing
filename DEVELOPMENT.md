# Development State

This file is the authoritative source of truth for session continuity. Every AI agent working on this project must read it fully before touching any code. It must be updated whenever meaningful decisions are made, bugs are found, architecture changes, or understanding deepens — not just at the end of a session. The goal is that a completely fresh context reading only this file can resume work at the same quality level as the context that wrote it.

---

## Instructions for the incoming agent — read this first, before everything else

You are resuming an ongoing collaborative project. Before you do anything — before you read any code, before you respond to the user, before you run any commands — read this entire document. It is not long for the sake of being long. Every section exists because a previous context learned something the hard way and documented it so you wouldn't have to.

### How to get fully caught up

Do these steps in order before engaging with any task:

1. **Read this entire file without skipping.** The section order is intentional. Philosophy before architecture, architecture before implementation, implementation before gaps. You need the philosophy to understand why the architecture is the way it is.

2. **Read every source file.** They are listed in the file map below with their implementation status. The files are not large. Read them all. Pay particular attention to the docstrings — they explain the "why" behind non-obvious decisions and contain unit information that has caused bugs before.

3. **Run `git log --oneline -20`** to see what has happened since this document was last updated. If commits exist that are not reflected in the session log at the bottom of this file, read the diffs and update your mental model accordingly.

4. **Check the known gaps section.** Before starting any new work, know which gaps exist. Do not accidentally build on top of a known broken assumption.

5. **Ask the user what they want to work on.** Do not assume. Do not jump into the most obvious next thing on the roadmap without confirming. The user may have context you don't.

### How to behave in this project

This is a collaborative project, not a task queue. The user is a capable engineer who wants to understand what is being built and why. They are not looking for an agent that silently executes instructions and produces output. They want a conversation.

**Be direct.** If you see a problem, say so. If the user's idea has a flaw, explain it clearly and propose the correct approach. Do not validate incorrect ideas to avoid friction. The user has explicitly stated they appreciate being corrected.

**Be conversational.** Respond like a knowledgeable colleague, not a documentation generator. Keep explanations tight and calibrated to the user's level. They have a deep C/systems background — you do not need to explain what a pointer is, but you should explain what adverse selection means.

**Ask before building.** If a task is ambiguous or has meaningful architectural implications, discuss it before writing code. The user cares deeply about code cleanliness. A five-minute conversation that clarifies requirements prevents a messy implementation that needs to be torn out.

**Never just do the obvious thing.** Before writing any code, think about whether it fits the existing architecture. If it doesn't fit cleanly, stop and discuss. The project has a strong separation of concerns: pure math in `src/core/`, ML in `src/ml/`, tax in `src/tax/`, all framework coupling in `controllers/`. Something that violates this is a design problem, not just a coding task.

**Do code reviews regularly.** The variance_term bug was caught in a review, not by tests (tests don't exist yet). Reviews should happen after any substantive implementation session. The format: silly mistakes first, then inefficiencies, then architectural oversights, then general correctness, then anything else that seems important.

**Update this document proactively.** Do not wait until the end of a session. If a decision is made, a bug is found, a gap is identified, or understanding deepens — update the relevant section immediately. Context degradation is the primary enemy of project quality over time.

---

## Project design philosophy

These are the principles that govern every decision in this project. When facing a choice that isn't covered by a specific guideline, these principles should resolve it.

### Mathematical foundation before machine learning

The Avellaneda-Stoikov model provides a theoretically grounded, mathematically derivable framework for market making. ML sits on top of it to estimate the one parameter (drift) that the model cannot derive from observable data alone, and to classify market regimes that determine how the model's parameters should be adjusted.

This ordering is deliberate and must be preserved. An end-to-end ML system that takes market data and outputs order prices is a black box. When it misbehaves — and it will — there is no principled way to debug it. You do not know whether it is failing because of a bad feature, a bad model, insufficient data, a regime shift, or a bug. You cannot audit it. You cannot explain to yourself or anyone else why it placed a specific order.

The A-S model is fully auditable. Given any market state, you can compute by hand what the bid and ask should be. When something seems wrong, you check the model inputs and verify the output against the formula. This property must be preserved as the project grows. ML should always be a narrow, targeted component with interpretable inputs and outputs, not a replacement for the core decision logic.

### No real money until the model is validated

Paper trading and exchange testnets exist specifically for this purpose. A strategy that looks reasonable in design can fail in ways that are only visible when running against real market data. The correct order is: paper trade → observe behavior → identify problems → fix → paper trade again → validate profitability → deploy live with small capital and hard limits.

Skipping any step in this sequence is how people lose real money. There is no urgency that justifies bypassing it.

### Clean code is not optional

The user stated this explicitly and it is a core project value. Maintainability matters more than cleverness, more than conciseness, and more than getting something working quickly. A working but messy solution is worse than a slightly delayed clean solution, because messy code compounds — every subsequent change becomes harder and more bug-prone.

Specific practices that follow from this:
- Before fixing a bug, think about whether the fix fits the existing structure or whether the structure itself needs to change.
- Never add a parameter, flag, or special case without asking whether the design should be reconsidered instead.
- If you find yourself writing a long comment to explain what code does, the code should probably be restructured to be self-explanatory.
- Comments explain why, not what. A comment that says "increment the counter" is worse than no comment.
- Functions do one thing. If a function is doing two things and both need explaining, it should be two functions.

### Safe defaults everywhere

Every component that has an "uninitialized" or "untrained" state must behave safely in that state. The ML models return zero drift and RANGING regime when no model is loaded. The inventory fallback returns 0.0 (with a warning) when the balance fetch fails. End-of-session behavior widens spreads to prevent fills rather than producing undefined behavior.

This principle extends to future development: any new component that can be in an incomplete state must define and implement its safe default behavior before it is integrated.

### Transparency over performance

Where there is a trade-off between a more efficient but opaque approach and a slightly less efficient but transparent approach, prefer transparency. This is a trading system. Understanding what it is doing and why — at every moment — is more important than squeezing out marginally better performance.

This does not mean being gratuitously slow. It means: don't use a clever bitwise trick where a readable conditional would do, don't compress logic into a one-liner that requires mental unpacking, and don't sacrifice legibility for a micro-optimization that has no measurable impact on the system's actual bottleneck (which is network latency, not CPU).

### Compliance is built in, not bolted on

Every trade is a potential taxable event. The trade logger is a first-class component, not an afterthought. Every fill, from the very first paper trade, is recorded with full IRS-required metadata. This approach costs almost nothing to maintain and avoids a painful reconstruction problem later.

Never disable or bypass trade logging, even during testing or debugging, unless you are certain you are not generating taxable events.

---

## User profile and working style

The user has a background in highly optimized C programming. They understand systems-level concepts deeply — memory, performance, concurrency, data structures — but are not a quant finance specialist. They learn quickly when explanations are grounded in systems analogies rather than finance jargon. They want the conversation to be collaborative and direct, not overly "agent-like." They will ask questions when they don't understand something and expect honest corrections when their intuitions are wrong.

Important working preferences:
- Code must be clean and maintainable above all else. If fixing a bug would introduce messiness, step back and find a clean approach. The user explicitly does not want a "muddy mud pile."
- Do not use emojis. Keep communication professional and direct.
- Never hide details or abstract away how something works for the sake of simplicity. The user wants to understand every mechanism — analogous to explicit stack allocation in C, where every byte moves because it was intended to, not because a heap allocator decided (this is a philosophical analogy about transparency and intentionality, not a statement about memory management in this project). Give full mechanical detail on how things work. What should be calibrated is the *level* of explanation (don't explain what a for loop is), not the *amount* of detail provided.
- Always be willing to correct the user when they have a wrong assumption. They appreciate it.
- Reviews of code should happen regularly. Asking an AI to review its own code catches real bugs.

---

## What this project is and why it exists

This is an advanced cryptocurrency market making bot built on top of Hummingbot V2. The high-level goal is to apply institutional-grade quantitative trading techniques — specifically market making — to cryptocurrency markets, which are more accessible and less efficient than traditional stock markets.

The inspiration came from hedge funds. Traditional hedge funds use sophisticated quantitative strategies on stock markets, but those markets are dominated by firms with massive infrastructure advantages (co-location, proprietary feeds, decades of data). Cryptocurrency markets are fragmented, trade 24/7, and are still less efficient, meaning the edge available to a well-designed systematic strategy is proportionally larger for a smaller operator.

The choice to build on Hummingbot rather than from scratch is deliberate: Hummingbot provides exchange connectors (REST and WebSocket), order management infrastructure, paper trading mode, and a clock/tick system. These are solved problems that would take significant time to build well. Our value-add is the strategy logic, ML layer, and tax pipeline on top of that foundation.

---

## Why market making and not directional trading

Directional trading means predicting whether a price will go up or down and taking a position accordingly. This sounds intuitive but is extremely difficult to do profitably over any meaningful time horizon. The market is full of participants attempting to do exactly this, including sophisticated quantitative funds with better data, faster execution, and more capital. The edge available to a retail-scale operator doing directional trading is thin at best.

Market making is structurally different. A market maker does not predict price direction. Instead, they continuously post a buy order slightly below the current fair price and a sell order slightly above it. When both sides fill, the market maker has captured the difference (the spread) as profit without taking any directional risk. The market maker acts as the shop rather than the customer — they provide liquidity to other traders who want to transact immediately.

Why this is more reliable for a systematic bot:
- The edge comes from the spread and from being on both sides of the market, not from price prediction, which is the hardest problem in finance.
- Returns are consistent across bull and bear markets. A market maker makes money in both directions as long as both sides of the book are active.
- The risk is well-defined and mechanical: inventory risk (holding too much of one asset when the price moves against you) rather than the open-ended risk of a wrong directional bet.
- Professional market making firms (Citadel Securities, Virtu Financial, Jane Street) are among the most consistently profitable businesses in all of finance. They profit in virtually every market condition.

The primary risk for a market maker is "adverse selection" — being filled repeatedly on one side by informed traders who know something about where the price is going, while the other side never fills. The Avellaneda-Stoikov model is specifically designed to manage this risk through inventory-aware spread and quote adjustment.

---

## Why cryptocurrency markets specifically

Several properties of crypto markets make them well-suited for this strategy:

1. **24/7 operation.** No overnight gaps, no market opens/closes to worry about. The bot can run continuously.
2. **Fragmentation.** Many exchanges trade the same assets, creating arbitrage and liquidity opportunities that don't exist in centralized traditional markets.
3. **Relative inefficiency.** Crypto markets are less mature than equity markets, meaning mispricings persist longer and the edge from a well-designed strategy is more durable.
4. **Accessibility.** CEX testnets with fake funds exist and are realistic. You can develop, test, and validate a strategy with zero real money at risk.
5. **Lower infrastructure requirements.** On equities, HFT firms are physically co-located with exchange servers. On crypto, a well-designed bot on a normal internet connection can compete meaningfully.

---

## Why paper trading first and why CEX over DEX

The decision to start with centralized exchange (CEX) paper trading rather than decentralized exchanges (DEX) is deliberate and important.

**CEX advantages for development:**
- Binance testnet provides fake funds and a realistic simulated order book. The paper trading environment is close enough to live trading that strategy validation there has real meaning.
- Order placement, cancellation, and fill events are simple HTTP/WebSocket calls. The API is well-documented.
- Hummingbot has mature, battle-tested CEX connectors. We do not need to write any exchange integration code.
- Fee structures are predictable and well-defined.

**DEX disadvantages for this stage:**
- Every transaction costs gas. Gas prices fluctuate, and the cost must be incorporated into the spread calculation or it will eat the strategy's profit.
- MEV (Maximal Extractable Value) bots front-run orders on DEXes. A market making strategy can be systematically exploited by these bots in ways that are very hard to model or defend against.
- Simulating DEX behavior accurately in paper trading is very difficult because of gas and MEV.
- Smart contract interaction adds a layer of complexity and failure modes.

DEXes are not ruled out permanently — they introduce interesting opportunities especially around liquidity pools — but they are a separate and more complex problem. Start with CEX.

**No real money until validated.** Paper trading produces realistic data for ML training (feature vectors and trade outcomes) and validates that the strategy is profitable before any capital is at risk. This is non-negotiable. The ML models should be trained on paper trading data before live deployment.

---

## Why Avellaneda-Stoikov and not Black-Scholes

This distinction is important to preserve because it comes up naturally and the relationship between the two models is easy to misunderstand.

**Black-Scholes** is an options pricing model. It answers: "What is the fair value of an options contract?" It models the underlying asset as a geometric Brownian motion with drift μ and volatility σ, and through a clever delta-hedging argument, derives that the option price is independent of drift — drift cancels out of the final equation. This is one of the most famous results in quantitative finance and is why Merton and Scholes won the Nobel Prize. Black-Scholes is a valuation tool, not a trading strategy. It has nothing to say about where to place limit orders.

**Avellaneda-Stoikov** is a market making model. It answers: "Given my current inventory, the market's volatility, and my risk tolerance, where should I place my bid and ask orders right now to maximize expected utility?" This is the problem we are solving.

The key insight of A-S is the **reservation price**: a risk-adjusted mid price that accounts for inventory. A dealer holding more base asset than they want will shade their quotes downward to encourage more selling and less buying, reducing their exposure. Conversely, a dealer who is short will shade upward. This inventory-aware adjustment is the core of the model.

In A-S, unlike Black-Scholes, drift does NOT cancel out. The drift term directly shifts the reservation price in the direction of predicted flow. This is precisely why the ML drift estimator is a meaningful and well-scoped component: it provides the one input the model cannot derive from the order book alone, and its effect is direct and interpretable.

The A-S closed-form solution produces:

```
Reservation price:  r = s + μ·(T-t) - q·γ·σ²·(T-t)
Optimal spread:     δ = γ·σ²·(T-t) + (2/γ)·ln(1 + γ/κ)
Bid:  r - δ/2
Ask:  r + δ/2
```

Where:
- `s` = current mid price
- `μ` = expected short-horizon drift (from ML estimator; 0 if unavailable)
- `q` = current inventory in base asset units (positive = long, negative = short)
- `γ` = risk-aversion parameter (higher = wider spreads, more aggressive inventory skewing)
- `σ` = volatility per second
- `T-t` = time remaining in session in seconds (not normalized — see the critical bug section)
- `κ` = order arrival rate intensity (higher = more liquid market = tighter optimal spreads)

---

## The ML architecture and why it is designed this way

The core design principle: **ML tunes parameters within the model; it does not replace the decision loop.**

An end-to-end learned system (e.g. "given order book data, output bid and ask prices directly") is a black box. When it misbehaves, diagnosing why is extremely difficult. It is also prone to overfitting and regime changes. A market making bot that malfunctions with real capital at stake needs to be debuggable.

Instead, the ML layer has two narrowly scoped jobs:

**1. Short-horizon drift estimation (DriftEstimator)**

The A-S model has one parameter that is genuinely unknown: the expected short-horizon drift of the asset price. The model defaults to zero drift, which is safe but suboptimal in trending conditions. A regression model trained on order book microstructure features outputs a drift estimate (in quote asset per second) that feeds directly into the reservation price calculation.

The key insight about this component: it is NOT trying to predict where the price will be in an hour or a day. It is predicting directional pressure over the next 30 seconds to a few minutes — the time scale at which the bot's current quotes will be live in the market. This is a much more tractable prediction problem than long-horizon forecasting.

**2. Market regime detection (RegimeClassifier)**

A classifier that identifies which of three market conditions currently prevails:
- **RANGING**: Normal conditions. The asset is trading sideways with no strong directional bias. Standard A-S parameters apply.
- **TRENDING**: Sustained directional pressure. The asset is moving strongly in one direction. Market making becomes more risky because you keep getting filled on the same side (adverse selection). The controller responds by skewing quotes more aggressively and halving order size to reduce exposure.
- **HIGH_VOLATILITY**: Chaotic conditions, large price swings. Spreads are widened by a configurable multiplier. If volatility is extreme enough, quoting should be suspended entirely. This is the equivalent of a market maker "stepping away" from the book when conditions are too risky.

**Why scikit-learn and not TensorFlow/PyTorch:**

The current implementation uses a Ridge regression pipeline for drift and a Random Forest pipeline for regime. This is deliberate:
- Both models are interpretable. You can inspect Ridge regression coefficients to understand which features are driving the drift signal. Random Forest provides feature importances for the regime classifier. When something seems wrong, you can actually look at what the model is doing.
- No GPU required. Training takes milliseconds on the amount of data we'll have initially.
- The interface is identical regardless of what's underneath (`predict(features)` returns a scalar or label). Upgrading to gradient boosting (XGBoost/LightGBM) or a sequence model (LSTM, Transformer) is a one-file change.
- scikit-learn models are significantly more appropriate for tabular feature data than deep learning at this scale. Deep learning tends to outperform on raw sequence input or image data, not on hand-engineered feature vectors.

The upgrade path when the baseline is proven insufficient:
1. Gradient boosting (XGBoost/LightGBM) — still tabular, significantly more expressive than linear/tree models, no deep learning complexity
2. LSTM/Transformer — when you want to process raw time series rather than hand-engineered features, and you have enough data to justify the complexity

Do not upgrade until paper trading data shows the current model is leaving measurable money on the table. Premature complexity is a trap.

**Why both models fall back to safe defaults when untrained:**

`DriftEstimator.predict()` returns `0.0` (zero drift assumption, identical to the original A-S paper) when no trained model is loaded. `RegimeClassifier.predict()` returns `MarketRegime.RANGING` (standard parameters) when no model is loaded. This means:
- The system runs correctly from day one with no ML infrastructure at all.
- Paper trading can begin immediately to collect the training data needed for the ML layer.
- There is never a hard dependency on having a trained model file present.
- The ML layer improves performance; it does not gate operation.

---

## Multi-scale feature engineering — the critical design distinction

The feature engineering design arose from the user's question about whether the drift estimator could look at longer-horizon data to avoid predicting noise. The answer is yes, but with an important distinction that must be preserved:

**Feature lookback window** (how far back you look to compute inputs): can and should be long. Using only 5-second order book snapshots gives noisy, hard-to-interpret signals. Including features derived from 5-minute momentum, 1-hour VWAP deviation, and multi-day trend direction dramatically improves signal quality. The longer-term features tell the model whether the current microstructure noise is occurring inside a sustained trend (in which case it should be weighted more heavily) or a ranging market (where it's more likely to mean-revert).

**Prediction horizon** (how far forward the model predicts): must remain short — seconds to low minutes. This is the time over which the bot's current quotes will be live. If you train the model to predict a 3-day forward return and feed that into a quote placement decision that executes in 30 seconds, the time horizon mismatch makes the drift term actively harmful rather than helpful.

The three feature groups in `src/ml/features.py`:

**Short-horizon features (seconds to ~5 minutes):**
- Order book depth imbalance (signed ratio of bid vs ask volume in top N levels)
- Trade flow directional skew (taker buy volume as fraction of total volume)
- Short-window simple return
- Short-window volatility
- Bid/ask spread in basis points
- Volume acceleration (current candle volume vs recent average)
- **Bar portion** (mean of `(close - low) / (high - low)` over the window; near 1.0 = bullish, near 0.0 = bearish, 0.5 = neutral fallback; OHLCV only, no book required; source: Stoikov et al. 2024, SSRN 5066176)
- **Spread timing** (`current_spread_bps / rolling_mean_candle_range_bps - 1`; negative = spread tighter than norm = order flow signals more reliable and persistent; IC increases 0.080→0.104 over time, unlike every other signal; rolling mean approximated from candle high-low ranges)

**Medium-horizon features (minutes to ~1 hour):**
- VWAP deviation (current price relative to volume-weighted average)
- Momentum at 1/4, 1/2, and full medium window
- Medium-window volatility
- Volume trend (recent vs historical average)

**Long-horizon features (hours to ~1 day):**
- Total return over the long window
- Linear regression slope as normalized trend strength
- Whether current price is above or below the long-window SMA

The key: all three groups feed into a single model that predicts short-horizon drift. The long-horizon features are contextual — they help the model understand the broader environment — but the target variable is always short-horizon.

---

## Stablecoins and inventory management

The user raised the idea of using stablecoins to "increase stability in times of chaos." This intuition is correct, and it is already built into the architecture in two ways:

**First:** When trading BTC-USDT, USDT is the quote currency and is already the "safe" side of the inventory. The A-S model continuously works to rebalance toward a neutral inventory position, which means it naturally pushes toward holding more USDT (the safe side) when BTC inventory builds up. Stablecoins-as-safe-haven is the implicit goal of inventory management.

**Second:** The HIGH_VOLATILITY regime is exactly the "chaos" condition the user described. When the regime classifier identifies it, the controller widens spreads and can suspend quoting entirely — which means the bot stops deploying capital into the volatile asset and sits in USDT. This is the computational equivalent of a flight-to-safety trade.

---

## Capital requirements and accessibility

The user was concerned about whether market making requires large capital like a hedge fund. It does not:

- You need enough capital to post orders that are large enough relative to exchange minimums and fee structures. On Binance, this is a few hundred to a few thousand dollars for the strategy to function correctly on BTC-USDT.
- The strategy scales proportionally. Smaller capital makes proportionally less profit per trade but the mechanics are identical.
- The main constraint is the spread-vs-fee ratio, not absolute capital size. On a liquid pair, spreads are tight and fees can eat them. On less liquid pairs, spreads are wider but inventory risk is higher. This balance is configurable.
- For paper trading, none of this matters — the bot uses fake balances.

---

## Python and performance

The user comes from a C background and naturally thinks about performance. For this application, Python's performance is not a meaningful constraint:

- The bottleneck is network round-trip time to the exchange, not CPU. A market making strategy at this scale places orders in response to market events that arrive over a network connection. The latency of a Python function call is irrelevant compared to the 5-100ms network round trip.
- The only place where Python performance would become a concern is very high-frequency tick-by-tick order book processing (sub-millisecond decisions). We are not operating at that frequency. Our strategy operates on candle intervals (1-minute minimum) and responds to fill events.
- The ML inference path (feature computation + model predict) runs in microseconds to low milliseconds, well within any reasonable tick interval.
- If a future version required HFT-class latency, the hot path would be rewritten in C/Rust and interfaced via Python FFI. But this is not a current concern and should not be introduced prematurely.

---

## Tax reporting and IRS requirements

Cryptocurrency transactions are required to be reported to the IRS. Specifically:
- Every disposal (sale) of a cryptocurrency is a potentially taxable event.
- Cost basis must be tracked from acquisition through disposal.
- Net gains and losses are reported on Form 8949 (individual transactions) and summarized on Schedule D.
- The IRS accepts three cost basis methods: FIFO (first in, first out), HIFO (highest in, first out — minimizes gains), and LIFO (last in, first out). FIFO is the default.

A market making bot that trades hundreds or thousands of times is creating hundreds or thousands of taxable events. Manual tracking is infeasible. The tax pipeline is a first-class feature of this project, not an afterthought.

The approach:
- Every fill is recorded to a JSONL log with all fields needed for Form 8949: timestamp, pair, side, quantity, price, fee, exchange.
- Paper trades are flagged `is_paper: True` and excluded from tax calculations.
- The cost basis module (Phase 3) will ingest the log and apply FIFO/HIFO/LIFO accounting.
- Output will be a Form 8949-compatible CSV and Schedule D summary.
- All computation is local. No trade data is sent to SaaS tax services — this was an explicit user requirement when they discovered most tax tools are cloud-based.

---

## File map and implementation status

```
src/
  __init__.py
  core/
    __init__.py
    avellaneda_stoikov.py     COMPLETE. Pure math. Zero external deps.
                              ModelParameters, MarketState, QuoteResult dataclasses.
                              compute_quotes() is a pure function.
                              inventory_is_at_limit() helper.
  ml/
    __init__.py
    features.py               COMPLETE. Multi-scale feature engineering.
                              OrderBookSnapshot dataclass.
                              compute_features() aggregates all three scale groups.
                              _short_features(), _medium_features(), _long_features() private.
                              Short features include bar_portion and spread_timing.
                              All private functions have full docstrings.
    drift_estimator.py        COMPLETE (infrastructure). No trained model yet.
                              DriftEstimator wraps sklearn Ridge pipeline.
                              Returns 0.0 when no model loaded.
                              train() and _persist()/_load_if_exists() implemented.
    regime_classifier.py      COMPLETE (infrastructure). No trained model yet.
                              RegimeClassifier wraps sklearn RandomForest pipeline.
                              Returns MarketRegime.RANGING when no model loaded.
                              MarketRegime enum: RANGING / TRENDING / HIGH_VOLATILITY.
  tax/
    __init__.py
    trade_logger.py           COMPLETE. Append-only JSONL log.
                              TradeRecord frozen dataclass — all Form 8949 fields.
                              TradeSide(str, Enum) for clean JSON serialization.
                              TradeLogger is thread-safe via threading.Lock.
                              read_taxable() filters paper trades automatically.

controllers/
  __init__.py
  avellaneda_stoikov_controller.py   IMPLEMENTED WITH KNOWN GAPS (see below).
                                     AvellanedaStoikovConfig (Hummingbot V2 config class).
                                     AvellanedaStoikovController (ControllerBase subclass).
                                     _extract_fee() helper for Hummingbot TradeFee.
                                     _parse_order_book() converts raw book to OrderBookSnapshot.
                                     _interval_to_seconds() raises on unknown unit.

scripts/
  hedge_bot.py                PARTIALLY IMPLEMENTED. Entry point thin wrapper.
                              HedgeBotConfig and HedgeBot classes exist.
                              init_markets() is a no-op — needs wiring (see gaps).

conf/scripts/
  conf_hedge_bot_1.yml.example   Config template. Copy to conf_hedge_bot_1.yml to run.

tests/
  __init__.py
  core/__init__.py             EMPTY — unit tests not yet written.
  ml/__init__.py               EMPTY
  tax/__init__.py              EMPTY

.cursor/rules/
  project-context.mdc          Cursor rule: always read DEVELOPMENT.md first.
  update-dev-state.mdc         Cursor rule: update DEVELOPMENT.md proactively.
```

---

## Architecture decisions with full reasoning

### `src/core/` has zero framework dependencies

The Avellaneda-Stoikov math in `src/core/avellaneda_stoikov.py` imports only the Python standard library (`math`, `dataclasses`). It has no knowledge of Hummingbot, pandas, numpy, or anything else.

**Why:** The pure math module can be unit tested, backtested, and reasoned about entirely independently of the trading infrastructure. When a critical bug was found in the variance_term calculation (see below), it could be identified and fixed in isolation. If the math lived inside the Hummingbot controller, testing it would require mocking the entire exchange connector stack.

**Invariant to preserve:** Never add framework imports to `src/core/`. If you need numpy in the math, reconsider whether the computation belongs there or in the controller/features module.

### Controller is the only file that imports Hummingbot

`controllers/avellaneda_stoikov_controller.py` is the integration boundary. It imports from Hummingbot and from our `src/` modules. Nothing else imports Hummingbot.

**Why:** This isolates all framework coupling to one file. If Hummingbot's API changes (it has changed significantly between V1 and V2), only the controller needs updating. The math, ML, and tax modules are unaffected.

**The `HUMMINGBOT_AVAILABLE` flag:** The controller wraps Hummingbot imports in a try/except and sets a flag. This allows the module to be imported in tests without a full Hummingbot install, which matters because setting up Hummingbot in a CI environment is non-trivial. The `AvellanedaStoikovConfig` class is only defined when Hummingbot is available, which creates a test-time limitation (the config class doesn't exist) that has not yet been resolved.

### ML models are infrastructure-ready but untrained

The `DriftEstimator` and `RegimeClassifier` classes have fully implemented training and persistence pipelines, but no trained model files exist. This is intentional, not an oversight.

**Why:** Training requires labeled data — (feature_vector, realized_drift) pairs for the drift estimator, and (feature_vector, regime_label) pairs for the classifier. The only valid source of this data for our specific trading pair, exchange, and time of day is live market data collected by the running bot. Synthetic data or data from a different exchange might produce a model that looks good in validation but fails live.

The workflow is: run paper trading → collect feature/label pairs → train → deploy. This cannot be shortcut. The fact that the models fall back to safe defaults means paper trading can begin immediately to start collecting data.

### `TradeSide` inherits from both `str` and `Enum`

```python
class TradeSide(str, Enum):
    BUY = "buy"
    SELL = "sell"
```

**Why:** When `asdict()` serializes a `TradeRecord` to a dict for JSON, standard Enum values become their Python object representation, not a string. By inheriting from `str`, `TradeSide.BUY` serializes as `"buy"` directly without needing a custom JSON encoder. This is important because the JSONL log must be human-readable and machine-parseable without any special deserialization logic.

### JSONL (newline-delimited JSON) for the trade log

Each line in `logs/trades.jsonl` is a complete, self-contained JSON object representing one trade.

**Why:** 
- Append-only: a single `f.write(line)` call is the only operation. No record is ever modified or deleted.
- Auditable: the file is the ground truth. If cost basis accounting produces a surprising result, you can open the file and read individual trades.
- Self-contained: each line has everything needed to reconstruct cost basis without cross-referencing other records. This matters because the IRS cares about acquisition date and price for each specific lot.
- Thread-safe: the `threading.Lock` in `TradeLogger` ensures no two threads can write simultaneously and corrupt a line.

### `frozen=True` on dataclasses

`ModelParameters`, `MarketState`, and `QuoteResult` are all frozen dataclasses. `TradeRecord` is also frozen.

**Why:** These objects represent snapshots — a model configuration at a point in time, a market state at a point in time, a trade that happened. They should not be mutable. Freezing them makes them hashable, prevents accidental in-place modification, and makes the data flow explicit: you don't modify a `QuoteResult`, you compute a new one.

### `compute_quotes()` is a pure function

It takes a `ModelParameters` and `MarketState` and returns a `QuoteResult`. No state, no side effects, no I/O.

**Why:** Pure functions are trivially testable (`assert compute_quotes(params, state).bid == expected`), safely callable from multiple threads, and trivially usable in backtesting without any mocking. The controller handles state; the math handles computation.

### Config lives in YAML, not hardcoded

The `AvellanedaStoikovConfig` Pydantic model serializes to and from YAML via Hummingbot's config system. All strategy parameters (gamma, kappa, time_horizon, order size, etc.) are configurable without code changes.

**Why:** The model parameters (especially gamma, kappa, and order size) will need to be tuned during paper trading. Being able to change them by editing a YAML file and restarting — rather than changing code — makes the tuning loop much faster and safer.

---

## Bugs found and fixed — do not re-introduce

### variance_term unit mismatch (critical)

**What was wrong:** In `compute_quotes()`, the variance term was computed as:
```python
variance_term = params.gamma * (state.volatility ** 2) * time_remaining
```
where `time_remaining` is a normalized [0, 1] ratio (fraction of session remaining).

**Why this was wrong:** `state.volatility` is expressed in units of **price per second** (σ per second). The A-S formula requires `σ² * (T-t)` where `T-t` is in **seconds**. Using a normalized [0, 1] ratio introduces a factor of `1/time_horizon` error. For a 3600-second session at `time_remaining = 1.0`, the variance term was 3600x too small, making spreads dramatically too narrow.

**What a too-narrow spread means in practice:** The bot would post quotes almost at the mid-price. Every informed trader who knows the price is about to move would immediately fill both sides. The bot would be systematically picked off with no spread revenue to compensate, bleeding money on every fill.

**The fix:**
```python
seconds_remaining = time_remaining * params.time_horizon
variance_term = params.gamma * (state.volatility ** 2) * seconds_remaining
```

The `drift_contribution` was already written correctly: `state.drift * seconds_remaining` (drift in price/second × seconds remaining = price contribution). Both terms now have consistent units.

### `_interval_to_seconds` silent fallback

**What was wrong:**
```python
return value * units.get(unit, 60)  # silently returned 60 for unknown units
```

**Why this was dangerous:** An unrecognized interval like `"1w"` (weekly) would silently compute volatility as if candles were 60 seconds long, producing a dramatically wrong volatility estimate with no indication anything was wrong.

**The fix:** Now raises `ValueError` with a descriptive message naming the invalid unit and listing valid options.

### Unused imports and dead code in controller

- `TrailingStop` was imported from Hummingbot but never used.
- `from dataclasses import replace` was imported inside `determine_executor_actions()` but `replace()` was never called — `QuoteResult(...)` is constructed directly. Dead import inside a method body.
- Both removed.

### Silent inventory fetch failure

**What was wrong:**
```python
except Exception:
    return 0.0
```

**Why this was dangerous:** If the connector temporarily fails to return a balance, the bot believes it has zero inventory. The inventory limit check (`inventory_is_at_limit()`) would then incorrectly allow orders that could breach the real position limit.

**The fix:** Exception is now logged with a warning message explaining what happened and that the 0.0 fallback may cause inaccurate inventory limits.

### Fee extraction assumed simple percentage

**What was wrong:** Fee was computed as `trade_fee.percent * fill_event.amount * fill_event.price`. This assumes the fee is always a percentage of the trade's notional value, which is one of two representations Hummingbot uses.

**Why this was wrong:** Hummingbot's `TradeFee` can represent fees as either:
1. `flat_fees`: a list of `(token, amount)` pairs — a fixed fee amount in a specific asset (e.g. 0.0001 BNB)
2. `percent + percent_token`: a percentage of trade value in a specific token

The original code would produce incorrect fee amounts when flat fees were used (very common on Binance when BNB fee discounts are active).

**The fix:** `_extract_fee()` helper function handles both cases. It prefers `flat_fees` when present (exact), falls back to `percent` (approximate, since we don't have the exact fill notional in that code path).

### `pyproject.toml` wrong build backend

**What was wrong:** `build-backend = "setuptools.backends.legacy:build"` — this path does not exist.
**The fix:** `build-backend = "setuptools.build_meta"` — the correct setuptools build backend.

### Removed unused dependencies

- `scipy` was listed as a dependency but is not used anywhere in the codebase. Removed.
- `jinja2` was listed as a core dependency but is only needed for Phase 3 tax form generation which is not yet implemented. Moved to `[project.optional-dependencies.tax]`.
- `pyyaml` was listed but Hummingbot handles YAML config internally. Removed.

---

## Known gaps — must be resolved before live trading

### Order cancellation (most critical architectural gap)

**The problem:** `determine_executor_actions()` creates new bid and ask executors every tick but never cancels existing ones. Each tick adds two more open orders. After 10 minutes of 1-second ticks, there are 1200 open orders. This would cause the exchange to rate-limit the bot and then likely flag the account.

**Why it's not fixed yet:** In Hummingbot V2, the correct way to cancel executors is to issue `StopExecutorAction` for each active executor's ID. The IDs of active executors are accessible via `self.executors_info`. However, the exact lifecycle — when an executor is considered "active" vs "filled" vs "cancelled" — needs to be verified against the running Hummingbot version before implementation. Guessing at this incorrectly could cause the bot to cancel orders that are mid-fill.

**What to do:** After installing Hummingbot and getting connectivity working, read the executor lifecycle documentation and look at existing V2 strategy examples (particularly `v2_with_controllers.py` in the Hummingbot repo). Then implement stale executor cancellation in `determine_executor_actions()` using `StopExecutorAction`.

**There is a prominent TODO comment in the code pointing to this gap.**

### `on_order_filled` hook may not fire on the controller

**The problem:** In Hummingbot V2's executor model, fill events are processed by executors, not delivered directly to controller methods. The `on_order_filled` method on `AvellanedaStoikovController` may never actually be called by the framework.

**What to do:** When Hummingbot is installed, verify this by adding a log statement to `on_order_filled` and placing a paper trade. If it doesn't fire, fills need to be captured by listening to Hummingbot's event bus or by reading executor state after fills complete.

### `scripts/hedge_bot.py` not fully wired

**The problem:** `HedgeBot.init_markets()` is a no-op. The controller is imported but not instantiated in the script. The V2 wiring pattern for connecting a script to a controller via the `controllers_config` field needs to be confirmed against the actual framework.

**What to do:** After Hummingbot is installed, look at `v2_with_controllers.py` in the Hummingbot scripts directory for the canonical wiring pattern and replicate it.

### No unit tests

**The problem:** The entire `tests/` tree is empty `__init__.py` files. The variance_term bug (the most critical bug found) was caught by manual code review, not by a test. If it had been caught by a test, it would have been caught earlier and with more precision.

**What to do:** Write tests for `src/core/avellaneda_stoikov.py` first. Key test cases:
- Zero inventory, zero drift: bid and ask should be symmetric around mid-price
- Positive inventory: bid should be below mid, ask should be above but bid closer to mid (skewed to sell)
- Negative inventory: opposite skew
- Zero time remaining: should return max-spread quotes
- `inventory_is_at_limit()` boundary conditions
- Verify units: at a 1-hour session (time_horizon=3600), the spread should scale appropriately with volatility

### `AvellanedaStoikovConfig` unavailable in tests

`AvellanedaStoikovConfig` is only defined inside `if HUMMINGBOT_AVAILABLE:`. In a test environment without Hummingbot installed, the class doesn't exist, which makes it impossible to construct a controller for testing. This needs a clean resolution — possibly a test-only mock config that satisfies the same interface.

---

## Roadmap

| Phase | Description | Status |
|---|---|---|
| 1 | Project structure, core A-S math, ML infrastructure, trade logger, Hummingbot controller scaffold | Complete |
| 1b | Unit tests for core math; verify Hummingbot connectivity; resolve order cancellation gap | In progress |
| 2 | Full Avellaneda-Stoikov strategy running in paper trading mode, fills logging correctly | Pending |
| 3 | Tax pipeline: cost basis accounting (FIFO/HIFO/LIFO), Form 8949 export, Schedule D summary | Pending |
| 4 | ML training loop: collect paper trading data, train drift estimator and regime classifier, integrate | Pending |
| 5 | Backtesting framework: replay historical candle data through the full strategy stack | Pending |
| 6 | Live deployment: hard position limits, kill switches, monitoring, gradual capital rollout | Pending |

---

## Long-term vision and business strategy

### Realistic return expectations

Target: 20-40% annually on deployed capital. This is exceptional by any normal investment standard (S&P 500 averages ~10%/year) and achievable with a well-implemented market making + funding rate arbitrage combination in normal market conditions.

The disappointment with "small scale = small absolute returns" is valid but misframes the goal. The near-term objective is not impressive dollar returns — it is proving the system works correctly and profitably in simulation. Once proven, capital scales the returns proportionally. The system itself is the asset being built right now.

Compounding math at 30% annually:
- $5k → $6.5k (year 1) → $11k (year 3) → $18.5k (year 5) → $69k (year 10)
- $50k → $65k (year 1) → $110k (year 3) → $185k (year 5) → $690k (year 10)

The moment the strategy is validated, adding capital is the lever. The compounding curve is nonlinear — patience with the early phase is the actual edge most people don't have.

### Why this is not like crypto mining

Mining became winner-take-all because it is purely a capital and electricity cost problem — no knowledge component, no insight that provides edge. Knowledge-based trading strategies are fundamentally different. Large firms (Citadel, Two Sigma) deliberately avoid strategies that produce less than tens of millions annually — those strategies are too small to be worth their operational overhead. A strategy producing $200-500k/year is worthless to them and completely viable for a small operator. This is a genuine structural advantage of being small.

### Future strategy research directions

Beyond market making, these are knowledge-based strategies worth researching — not speed or scale dependent:

**Funding rate arbitrage (crypto-specific, high priority)**
On perpetual futures, a funding rate is paid between longs and shorts every 8 hours. During bull market euphoria, rates can reach 0.1% per 8 hours (100%+ annualized). Capture by going long spot and short the perpetual simultaneously — you earn the funding rate with near-zero directional risk. Highly profitable in certain market conditions, dormant in others. Natural complement to market making: when funding rates are high, run arb; when they're low, run market making. Requires capital deployed on both a spot and futures exchange.

**Cross-exchange order book microstructure**
Most strategies look at one exchange. The relationship between order book depth on Binance vs Coinbase vs Kraken for the same asset contains information about where informed order flow is concentrated. When books are asymmetric across exchanges in the same direction, it often precedes a move. Underexplored because it requires ingesting multiple feeds simultaneously — a data infrastructure problem, not a math problem.

**Medium-frequency order flow imbalance (1 second to 5 minutes)**
Too slow for HFT, too fast for most retail strategies. Academic research suggests predictable patterns at this scale based on order book imbalance that HFT firms deliberately ignore because the per-trade profit is below their threshold. Our ML drift estimator is already positioned here — this is worth pursuing further.

**Abandoned strategies worth revisiting in crypto context**
Pairs trading and mean reversion "stopped working" in equities as they got crowded. In crypto, correlations between assets shift dramatically with market regimes for mechanical reasons (capital rotation), not just statistical noise. The conditions that made these strategies work may still exist in crypto's less mature market structure.

Academic reading worth doing: Glosten-Milgrom model, Kyle model (limit order book microstructure). Genuine signal there that hasn't been fully industrialized yet.

---

### Research findings (April 2026 — from live literature search, not training data)

**Order flow imbalance — quantified signal decay:**

From Delphi Alpha's Crypto Orderflow Alpha Report (January 2026), analyzing 1-second L2 order book snapshots:

- Queue Imbalance Top1 (ratio of best-bid size to best-ask size): IC = 0.129 at 10s horizon, 0.065 at 60s, 0.023 at 600s. Decays ~50% every 60 seconds. Still significant at 10 minutes.
- OFI (Order Flow Imbalance — normalized arrivals and cancellations): IC 0.016-0.023. Lower but independent of the imbalance signal. Using both together gives higher combined IC than either alone.
- **"Spread Timing" signal (underexplored, actionable):** IC *increases* from 0.080 at 10s to 0.104 at 120s. This is the opposite of every other signal. It captures whether spreads are currently tight relative to normal — when spreads are tight, order flow signals persist longer and are more reliable. Implication for us: when spread_bps is low, weight the drift estimate more heavily in the reservation price calculation. We should add this feature explicitly.
- Deeper book levels (Top10) are more persistent but lower IC. Top1 is the best signal.
- Simple models (XGBoost, logistic regression) match or exceed CNN+LSTM on LOB data with good feature engineering. Validates our Ridge baseline.
- Signal is not standalone profitable due to fees (~10bps round-trip). Best used as a feature improving a broader model — exactly what we're doing.

arxiv paper 2602.00776 (Jan 2026, CatBoost across multiple crypto assets 2022-2025): confirms the same SHAP patterns are "remarkably stable cross-asset" — order flow imbalance, spreads, VWAP-to-mid deviations drive predictions consistently across BTC, ETH, and altcoins. Validates that a model trained on BTC transfers to ETH with minimal retraining.

**Funding rate arbitrage — concrete 2025-2026 numbers:**

| Market condition | Single exchange APR | Cross-exchange APY |
|---|---|---|
| Strong bull (Q4 2024) | 27.4% | 20-28% |
| Moderate bull (Q2 2025) | 16-27% | 15-22% |
| Neutral/ranging | ~11% | 10-15% |
| Low-vol/bear (early 2026) | 5.5-10% | 8-12% |

18-month backtest (Sept 2022-March 2024): 156% cumulative return, Sharpe ratio 1.42, max drawdown 18% (FTX collapse when funding went deeply negative). Strategy recovered fully.

Critical fee constraint discovered: at 0.025% funding spread with 0.01% fees per side × 4 sides = 0.04% in fees, the strategy is NEGATIVE. At 0.005% fees (VIP tier) it produces 0.004% net per 8h. Fee optimization is not optional for cross-exchange arb — it determines whether the strategy exists at all. Minimum capital $5k-10k per exchange to reach favorable fee tiers.

For SOL, DOGE, and meme coins: funding spreads are 2-3x higher than BTC (SOL averages 0.022%/8h spread, memes 0.045%+). Higher yield but thinner books and execution risk.

**The novel angle: bidirectional funding rate arb with regime detection**

The main risk in funding arb is a funding rate flip (positive → negative), which happened during FTX. The standard strategy takes losses during flips. An enhancement nobody in retail is doing automatically: detect the flip and reverse the position (short spot + long perp instead of long spot + short perp), converting a drawdown into additional yield. Our existing regime classifier is already architecturally positioned to detect this. This is a genuinely underexplored combination.

**Directly relevant paper: "Market Making in Crypto" (SSRN 5066176, Cornell, Dec 2024)**
Authors: Sasha Stoikov et al., Cornell Financial Engineering Manhattan. Stoikov is the same person who co-authored the original 2008 Avellaneda-Stoikov paper we are implementing. He is still active and building on his own model.

The paper develops a signal called "Bar Portion" (BP) — almost certainly `(close - low) / (high - low)` per candle, measuring where the close sits within the candle's high-low range. Value near 1.0 = closed near the high (bullish pressure). Value near 0.0 = closed near the low (bearish pressure). Averaged over a short window, this becomes a directional drift signal.

Key properties that make it valuable alongside order flow imbalance:
- Measures *outcome* (where did price end up?) rather than *pressure* (what was the book doing?). Low correlation with imbalance features = genuinely additive information.
- Derived purely from OHLCV candles — no live order book required. Available from any exchange, any pair, any historical source.
- Confirmed robust across cryptocurrencies in the paper.

Live-traded on Hummingbot (SOL-USDT, DOGE-USDT, GALA-USDT perpetuals) and outperformed MACD baseline.

**Implementation for `_short_features()` in `src/ml/features.py`:**
```python
high = recent["high"]
low = recent["low"]
close = recent["close"]
range_ = (high - low).replace(0, float("nan"))
bar_portion = ((close - low) / range_).mean()
features["bar_portion"] = float(bar_portion) if np.isfinite(bar_portion) else 0.5
```
Use 0.5 as fallback (neutral, no directional signal) rather than 0.0.

Also noted: Hummingbot's built-in V1 `avellaneda_market_making` strategy estimates kappa automatically from the order book via a `trading_intensity` indicator. Compare against our manual kappa config once the Docker run is working — may be worth borrowing their estimator.

### Business model and scaling path

**Phase 1 — Prove the strategy (now)**
Paper trade → validate profitability → deploy small real capital ($1k-5k). Goal is not impressive returns, it is proof that the system works.

**Phase 2 — SaaS/platform model (cleanest path to scale)**
Rather than a fund (which triggers securities law), build a platform where users connect their own exchange API keys and the bot trades on their behalf using their own capital. They never give you their money — you provide a service. Charge a performance fee (e.g. 20% of profits) or monthly subscription.

This sidesteps the accredited investor problem entirely: users own their capital at all times, so there is no pooled investment vehicle and no securities offering. This is how legitimate retail algo trading platforms operate. The controller already manages one account; managing N accounts is an infrastructure problem, not a strategy problem.

**Phase 3 — Capital raising if desired**
If raising external capital later, legitimate paths for non-accredited investors:
- **Regulation Crowdfunding (Reg CF):** Up to $5M/year from general public. Requires SEC filings and a registered crowdfunding platform. Real overhead but manageable.
- **Regulation A+ (mini-IPO):** Up to $75M from general public. More overhead, serious capital potential.
- **Operating company structure:** A technology company that develops trading software and deploys its own capital is a legitimate business. Investors buy equity in the business, not fund units. The SEC looks at substance — if it looks like a fund in substance, it will be treated as one regardless of corporate form. Consult a securities lawyer before structuring this.

**Important legal caveat:** The above is general information, not legal advice. Before raising any external capital in any form, consult a securities attorney. The penalties for unregistered securities offerings are severe.

---

## Trading pair selection

**Primary pair: BTC-USDT**

This is the correct starting pair for the following mechanical reasons:

- **Liquidity:** Highest volume on every major CEX. Deep order books mean both sides fill regularly. A market maker with a thin book on one side accumulates lopsided inventory, which is exactly the risk A-S is designed to manage — but it works best when fill rates on both sides are roughly balanced.
- **Spread-to-fee ratio:** On Binance, maker fees are 0.1% (lower with BNB discount). BTC-USDT spreads are consistently wide enough to clear this bar. Tighter pairs like stablecoin-stablecoin have spreads so narrow that fees consume all profit at our scale.
- **ML training quality:** BTC-USDT microstructure features will have the clearest signal. The drift estimator and regime classifier will be most reliable on the most liquid, most-traded pair. Training on an illiquid alt produces a brittle model that doesn't generalize.
- **Reference asset properties:** BTC leads the market. When conditions shift, BTC moves first, giving the regime classifier the clearest signal to learn from.

**Secondary pair (future): ETH-USDT**

Same reasoning as BTC — deep, liquid, well-behaved. Natural expansion once BTC-USDT is validated and profitable. Run as a second independent controller instance, not a modification to the existing one.

**Why not altcoins:**
- Wider spreads are appealing but inventory risk is much higher. An alt can drop 20% in minutes with no news.
- Thin order books mean our orders move the market, which violates the A-S model's assumption that we are a small participant relative to total volume.
- ML models trained on BTC will not transfer to alts without full retraining.

**Why not stablecoin pairs (e.g. USDC-USDT):**
- Spreads are microscopic (fractions of a basis point). Exchange fees consume all profit at our capital scale.

---

## Docker setup — completed

Hummingbot runs via Docker, not a native install. This was chosen deliberately to avoid touching the host system, sidestep a known-broken Python/Darwin installation on the user's Mac, and ensure reproducibility.

**Key facts about the Docker setup:**
- Image: `hummingbot/hummingbot:version-2.13.0` (pinned, not `latest`)
- Platform: `linux/amd64` — runs via Rosetta 2 on Apple Silicon. Docker Desktop handles this transparently. You will see a platform mismatch warning on pull; this is expected and harmless.
- `docker-compose.yml` is in the repo root. All configuration is there.
- `CONFIG_PASSWORD=dev` is set in the compose file. Hummingbot encrypts its config files at rest and will prompt for this on first start.
- `PYTHONPATH=/home/hummingbot` is set so `from src.core...`, `from src.ml...`, `from src.tax...` all resolve inside the container.

**Volume mounts — how our code gets into the container:**
```
./scripts     → /home/hummingbot/scripts      (Hummingbot finds hedge_bot.py here)
./controllers → /home/hummingbot/controllers  (Hummingbot finds the controller here)
./src         → /home/hummingbot/src          (our library code, importable via PYTHONPATH)
./conf        → /home/hummingbot/conf         (strategy YAML config files)
./logs        → /home/hummingbot/logs         (trade logs, Hummingbot logs)
./data        → /home/hummingbot/data         (Hummingbot's SQLite state)
```
All edits to source files in the repo are immediately live in the container — no rebuild needed.

**How to run:**
```bash
# Copy the example config first (only needed once)
cp conf/scripts/conf_hedge_bot_1.yml.example conf/scripts/conf_hedge_bot_1.yml

# Start the interactive Hummingbot CLI
docker compose run --rm hedge-bot
```
`--rm` cleans up the container on exit. All persistent state lives in the mounted volumes, not the container, so nothing is lost.

Inside Hummingbot, to start the strategy:
```
start --v2 conf/scripts/conf_hedge_bot_1.yml
```

**Docker Desktop note for the user's machine:**
The user's Docker Desktop was previously running Open WebUI and related containers in a restart loop, consuming all CPU/RAM. Those have been fully cleaned out. Docker is now empty. The Hummingbot image pull (`docker compose pull`) was in progress at the end of the last session and may need to be re-run if it did not complete.

---

## Immediate next steps (in priority order)

These are the exact tasks to work on next, in this order. Do not skip ahead.

1. **Do the first Docker run and fix whatever breaks.**
   The Docker image is already pulled (`hummingbot/hummingbot:version-2.13.0`). The config file already exists (`conf/scripts/conf_hedge_bot_1.yml`). Run `docker compose run --rm hedge-bot` from the repo root. Type `dev` for the config password. Then inside Hummingbot run `start --v2 conf/scripts/conf_hedge_bot_1.yml`. Observe errors. The likely failures are: (a) script wiring in `hedge_bot.py` is incomplete, (b) import errors for our src modules. Fix them as they appear.

2. **Resolve script wiring in `scripts/hedge_bot.py`.**
   The current file is a stub. Look at Hummingbot's `v2_with_controllers.py` example inside the running container at `/home/hummingbot/scripts/` to see the canonical V2 controller-to-script wiring pattern, then replicate it.

3. **Verify executor lifecycle and implement order cancellation.**
   Critical architectural gap — the controller creates new orders every tick but never cancels stale ones. Read the executor API from a running strategy, then implement `StopExecutorAction` for stale orders before creating new ones in `determine_executor_actions`.

4. **Verify `on_order_filled` fires on the controller.**
   Place a paper trade and check logs. If it doesn't fire, capture fills via executor state or event bus instead.

5. **Write unit tests for `src/core/avellaneda_stoikov.py`.**
   The variance_term bug was caught by review, not tests. Tests in `tests/core/test_avellaneda_stoikov.py`.

---

## Session log

| Date | What happened |
|---|---|
| 2026-04-25 | Initial project. Discussed market making vs directional trading, A-S vs Black-Scholes, ML architecture, stablecoins/inventory, CEX vs DEX, Python performance. Implemented all Phase 1 files. Code review found and fixed: variance_term unit bug (critical), _interval_to_seconds silent fallback, unused imports, silent inventory exception, wrong fee extraction, wrong pyproject.toml build backend, removed scipy and jinja2 from core deps. Identified order cancellation gap and on_order_filled uncertainty. Created DEVELOPMENT.md and Cursor rules for session continuity. Added Docker setup (docker-compose.yml, volume mounts, PYTHONPATH). Cleaned Docker Desktop of all previous containers/images. Hummingbot image pull started but may not have completed at session end — re-run `docker compose pull` to confirm. |
| 2026-04-25 | New session (context reset). Added `bar_portion` and `spread_timing` to `_short_features()` in `src/ml/features.py`. Self-review found and fixed: "Log-return" docstring mismatch (code computed simple return), missing docstrings on `_medium_features` and `_long_features`, misleading `compute_features` docstring re: NaN fill behavior for domain-specific defaults. File map status for `features.py` updated to reflect new features. Spread timing task removed from next-steps list. |
