# LastEdge Strategy Lab — Walk Forward Analysis (WFA)

> **Module:** `LastEdge Strategy Lab`  
> **Source File:** `core/walkforward.py`  

---

## 1. Walk Forward Methodology

Walk Forward Analysis tests whether optimized parameters hold predictive power on subsequent unseen market data.

```text
Full Historical Data
─────────────────────────────────────────────────────────────────────────────►
Window 1: [   In-Sample Train (70%)   ][ Out-of-Sample Test (30%) ]
Window 2:       [   In-Sample Train (70%)   ][ Out-of-Sample Test (30%) ]
Window 3:             [   In-Sample Train (70%)   ][ Out-of-Sample Test (30%) ]
Window 4:                   [   In-Sample Train (70%)   ][ Out-of-Sample Test (30%) ]
```

---

## 2. Walk Forward Efficiency Score (WES)

$$\text{WES} = \frac{\text{Annualized Return (Out-of-Sample Concatenated)}}{\text{Annualized Return (In-Sample Average)}}$$

- **$\text{WES} \ge 0.60$**: **Pass**. Robust strategy with real out-of-sample edge.
- **$\text{WES} < 0.50$**: **Fail**. Indicative of severe parameter curve-fitting.
