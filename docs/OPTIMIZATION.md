# LastEdge Strategy Lab — Strategy Parameter Optimization

> **Module:** `LastEdge Strategy Lab`  
> **Source Files:** `run_validation.py`, `core/scoring.py`  

---

## 1. Parameter Grid Search

Optimization is performed strictly over robust parameter ranges (e.g. EMA periods 15..30 in steps of 5, ATR multipliers 1.5..3.0 in steps of 0.5) to avoid fragile point-solutions.

---

## 2. Objective Functions & Multivariable Scoring (`core/scoring.py`)

Instead of optimizing solely for total net profit, LastEdge optimizes for a balanced fitness function:

$$\text{Fitness Score} = \text{Sharpe Ratio} \times \text{Profit Factor} \times (1 - \text{Max Drawdown Pct}) \times \ln(\text{Trade Count})$$

- Penalizes strategies with high drawdown or low trade frequency.
- Prefers smooth equity curves with consistent statistical expectancy.
