# LastEdge Strategy Lab — Quantitative Research Pipeline & Modeling

> **Module:** `LastEdge Strategy Lab`  
> **Source Packages:** `core/replay_engine.py`, `core/trade_costs.py`, `core/exit_research/`, `run_pipeline.py`  
> **Status:** Production Standard  

---

## 1. The Quantitative Research Methodology

LastEdge adheres to a strict scientific methodology designed to eliminate curve-fitting, lookahead bias, and data-snooping:

```text
[1. Market Inefficiency Hypothesis] ──► [2. BaseStrategy Prototype Implementation]
                                                        │
                                                        ▼
[4. Bar-by-Bar Replay with Costs]   ◄── [3. Offline DataLoader Ingestion]
        │
        ├── Gross PnL - Spread - Commissions - Slippage
        ▼
[5. Parameter Optimization & Scoring] ──► [6. Exit Research Framework]
        │                                         │ (Trailing, Partial, Breakeven)
        ▼                                         ▼
[7. Multi-Metric Robustness Validation] ──► [8. Promotion to Production]
```

---

## 2. Realistic Trade Cost & Friction Modeling (`core/trade_costs.py`)

Simulations without frictional costs yield deceptive results. Every simulated fill accounts for:

$$\text{Net PnL} = \text{Gross PnL} - \text{Spread Cost} - \text{Commission} - \text{Slippage}$$

- **Spread Cost:** Deducts entry and exit half-spreads derived from instrument historical distributions or fixed spread matrices.
- **Broker Commission:** Models ECN/Raw commission structures ($6.00 per round-turn lot).
- **Slippage Model:** Applies stochastic slippage penalties to emulate execution latency during fast markets.

---

## 3. Bar-by-Bar Replay Engine (`core/replay_engine.py`)

The replay engine iterates sequentially through historical data:
1. **Indicator Warmup:** Feeds `required_history` bars (minimum 50 bars) to ensure all indicators (EMAs, ATRs, RSI, Session Swings) stabilize.
2. **Signal Evaluation:** Invokes `detect_setup(df_window)` on bar close.
3. **Intrabar Execution:** Uses subsequent bar Open/High/Low to verify exact Stop Loss, Take Profit, or Trailing Stop executions.

---

## 4. Parameter Optimization & Multivariable Scoring (`core/scoring.py`)

Optimization is conducted over discrete, robust parameter grids to avoid fragile point-solutions. The fitness function balances returns, drawdowns, and sample size:

$$\text{Fitness Score} = \text{Sharpe Ratio} \times \text{Profit Factor} \times (1 - \text{Max Drawdown Pct}) \times \ln(\text{Trade Count})$$

- Heavily penalizes models with high drawdowns or low statistical trade counts ($N < 50$).
- Favors smooth, continuous equity curves over sporadic windfall spikes.

---

## 5. Exit Research Framework (`core/exit_research/`)

Decouples signal generation from exit mechanics to evaluate exit rules across identical entry vectors:

```text
[BaseStrategy (detect_setup)] ──► [StrategyAdapter] ──► [ExitResearchRunner]
                                                                │
                                 ┌──────────────────────────────┼──────────────────────────────┐
                                 ▼                              ▼                              ▼
                          [Variant A: Fixed]           [Variant B: Trailing]          [Variant C: Partial]
                          (Fixed R:R 1:2)              (ATR 1.5x Trailing)            (50% TP1 + Trailing)
```

### Supported Exit Variants (`core/exit_research/variants.py`):
- **Fixed Target:** Standard static Risk:Reward targets (e.g. 1.5R, 2.0R).
- **Dynamic Breakeven:** Protects entry capital by ratcheting Stop Loss to entry once price advances $+1.0 \times \text{ATR}$.
- **ATR Trailing Stop:** Continuously trails Stop Loss at a multiple of ATR below/above the extreme high/low.
- **Partial Take Profit:** Realizes 50% profit at Target 1 and trails the remaining volume to capture tail trends.

---

## 6. Unified Research CLI (`run_pipeline.py`)

The full quantitative pipeline can be executed in a single command:

```bash
# Full offline research run on EURUSD
python run_pipeline.py --symbol EURUSD --strategy eurusd_simple --bars 20000

# Research run with automatic candidate evaluation and promotion gate check
python run_pipeline.py --symbol XAUUSD --strategy xauusd_simple --promote
```

---

## 7. Research Acceptance Thresholds

Before a model is eligible for promotion, it must satisfy all quantitative gates:
- **Profit Factor (Out of Sample):** $\ge 1.35$
- **Sharpe Ratio (Annualized):** $\ge 1.20$
- **Max Drawdown (Monte Carlo 99% CI):** $\le 15.0\%$
- **Walk Forward Efficiency Score (WES):** $\ge 0.60$
- **Total Trades (Out of Sample):** $\ge 150$ trades
