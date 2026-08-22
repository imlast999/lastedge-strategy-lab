# LastEdge Strategy Lab — Multi-Year Validation Framework

> **Module:** `LastEdge Strategy Lab`  
> **Source Files:** `run_long_forward_validation.py`, `services/long_forward_validation.py`  

---

## 1. Long-Period Out-of-Sample Testing

`run_long_forward_validation.py` tests strategies across 5+ years of historical market regimes (ranging, trending, flash crashes, high interest rate cycles) to verify edge longevity.

---

## 2. Robustness Criteria

- **Max Annual Drawdown**: Never exceeds $15\%$ in any individual calendar year.
- **Positive Expectancy in 80%+ of rolling 6-month windows**.
- **No sensitivity to small slippage/spread variations** ($\pm 20\%$ spread stress test).
