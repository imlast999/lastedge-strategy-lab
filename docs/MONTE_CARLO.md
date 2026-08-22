# LastEdge Strategy Lab — Monte Carlo Simulation Engine

> **Module:** `LastEdge Strategy Lab`  
> **Source File:** `core/montecarlo.py`  

---

## 1. Simulation Methodology

The Monte Carlo engine tests sequence and order risk by randomly reshuffling trade return records (bootstrap without replacement by default, or with replacement optionally) across $N = 5{,}000$ iterations (`DEFAULT_N_SIMULATIONS = 5000`).

---

## 2. Statistical Metrics & Outputs

- **Drawdown Distribution**: Computes 5th, 25th, 50th (median), 75th, 95th, and 99th percentile maximum drawdowns.
- **Profit Factor Distribution**: Percentile curves for expected profit factors under random trade ordering.
- **Risk of Ruin**: Probability that equity drops below the ruin threshold (default: $-30\%$ of initial equity).
- **Consecutive Loss Streaks**: Expected maximum sequence of consecutive losing trades.
