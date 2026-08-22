# LastEdge Strategy Lab — Monte Carlo Simulation Engine

> **Module:** `LastEdge Strategy Lab`  
> **Source File:** `core/montecarlo.py`  

---

## 1. Simulation Methodology

The Monte Carlo engine tests sequence risk by randomly reshuffling trade return series 1,000 to 5,000 times (with replacement / bootstrap sampling).

---

## 2. Statistical Outputs

- **Drawdown Distribution**: Calculates 50th, 90th, 95th, and 99th percentile maximum drawdown.
- **Risk of Ruin**: Probability of equity dropping below a critical threshold (e.g. 20% drawdown) during a 500-trade sequence.
- **Max Consecutive Losses**: Distribution of worst losing streaks expected over a multi-year horizon.
