# LastEdge Strategy Lab — Walk Forward Analysis (WFA)

> **Module:** `LastEdge Strategy Lab`  
> **Source File:** `core/walkforward.py`  

---

## 1. Walk Forward Methodology

Walk Forward Testing divides historical market data into overlapping train/test windows and runs the replay engine sequentially to detect parameter curve-fitting:

```text
Historical Data
─────────────────────────────────────────────────────────────────────────────►
Window 1: [   TRAIN (4,320 bars ~ 6m)   ][ TEST (720 bars ~ 1m) ]
Window 2:         [   TRAIN (4,320 bars ~ 6m)   ][ TEST (720 bars ~ 1m) ]
Window 3:                 [   TRAIN (4,320 bars ~ 6m)   ][ TEST (720 bars ~ 1m) ]
```

---

## 2. Window Configuration & Constants

- **`DEFAULT_TRAIN_BARS`**: 4,320 bars (~6 months of H1 data).
- **`DEFAULT_TEST_BARS`**: 720 bars (~1 month of H1 data).
- **`DEFAULT_STEP_BARS`**: 720 bars (advances 1 month per iteration).

---

## 3. Walk Forward Efficiency Score (WES)

$$\text{WES} = \frac{\text{Test Net Pips}}{\text{Train Net Pips}} \times \frac{\text{Test Win Rate}}{\text{Train Win Rate}}$$

- **$\text{WES} \ge 0.60$**: **Pass**. Robust strategy with verified out-of-sample edge.
- **$\text{WES} < 0.50$**: **Fail**. Indicative of parameter overfitting.
