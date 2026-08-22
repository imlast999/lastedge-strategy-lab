# LastEdge Strategy Lab — Scientific Research Workflow

> **Module:** `LastEdge Strategy Lab`  
> **Lifecycle:** Research -> Validation -> Candidate -> Promotion  

---

## 1. The Quantitative Research Pipeline

LastEdge follows a rigorous empirical research framework to prevent curve-fitting and survivorship bias:

```text
[1. Market Hypothesis]
  - Formulate market inefficiency / structural edge (e.g. regime momentum, Asian range breakout).
       │
       ▼
[2. Prototype Implementation]
  - Implement class inheriting from BaseStrategy in `strategies/experimental/`.
       │
       ▼
[3. In-Sample Backtest with Full Costs]
  - Run backtest modeling spread, commission, and slippage (`core/trade_costs.py`).
  - Calculate Sharpe (> 1.2), Profit Factor (> 1.4), Max Drawdown (< 15%).
       │
       ▼
[4. Walk Forward Analysis (WFA)]
  - Evaluate parameter stability across rolling out-of-sample windows (`core/walkforward.py`).
  - Target WFA Efficiency Score (WES) >= 0.60.
       │
       ▼
[5. Monte Carlo Stress Testing]
  - Run 1,000 reshuffled paths (`core/montecarlo.py`).
  - Verify max drawdown at 99% confidence interval is within risk limits.
       │
       ▼
[6. Exit Research Optimization]
  - Test exit variants (Trailing, Partial, Breakeven) using `core/exit_research/`.
       │
       ▼
[7. Candidate Registration]
  - Freeze configuration parameters and save record in `data/candidates/*.json`.
  - Calculate `config_hash` and `code_sha256`.
       │
       ▼
[8. Promotion Approval & Export]
  - Export verified `.py` file to `Trading Engine/strategies/` for production.
```

---

## 2. Research Success Metrics

A candidate must pass all following quantitative gates before registration:

- **Profit Factor (Out of Sample)**: $\ge 1.35$
- **Sharpe Ratio (Annualized)**: $\ge 1.20$
- **Max Drawdown (Monte Carlo 99% CI)**: $\le 15.0\%$
- **WFA Efficiency Score (WES)**: $\ge 0.60$
- **Total Trades (Out of Sample)**: $\ge 150$ trades
