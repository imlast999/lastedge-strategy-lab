# LastEdge Strategy Lab — Multi-Level Validation & Stress Testing

> **Module:** `LastEdge Strategy Lab`  
> **Source Files:** `core/walkforward.py`, `core/montecarlo.py`, `run_validation.py`, `run_long_forward_validation.py`  
> **Status:** Production Standard  

---

## 1. Overview of Validation Framework

Validation is the defensive gatekeeper of Strategy Lab. A strategy with stellar in-sample backtest results must demonstrate statistical robustness under rolling out-of-sample windows, order permutations, and multi-year regime changes.

---

## 2. Walk Forward Analysis (WFA) (`core/walkforward.py`)

Walk Forward Testing divides historical market data into overlapping train/test windows and executes the replay engine sequentially to detect parameter curve-fitting:

```text
Historical Data
─────────────────────────────────────────────────────────────────────────────►
Window 1: [   TRAIN (4,320 bars ~ 6m)   ][ TEST (720 bars ~ 1m) ]
Window 2:         [   TRAIN (4,320 bars ~ 6m)   ][ TEST (720 bars ~ 1m) ]
Window 3:                 [   TRAIN (4,320 bars ~ 6m)   ][ TEST (720 bars ~ 1m) ]
```

### Standard Window Constants:
- **`DEFAULT_TRAIN_BARS`**: 4,320 bars (~6 months of H1 data).
- **`DEFAULT_TEST_BARS`**: 720 bars (~1 month of H1 data).
- **`DEFAULT_STEP_BARS`**: 720 bars (advances 1 month per iteration).

### Walk Forward Efficiency Score (WES):
$$\text{WES} = \frac{\text{Test Net Pips}}{\text{Train Net Pips}} \times \frac{\text{Test Win Rate}}{\text{Train Win Rate}}$$

- **$\text{WES} \ge 0.60$**: **Pass**. Robust strategy with verified out-of-sample edge.
- **$\text{WES} < 0.50$**: **Fail**. Indicative of parameter overfitting.

---

## 3. Monte Carlo Simulation Engine (`core/montecarlo.py`)

The Monte Carlo engine tests sequence and order risk by randomly reshuffling trade return records across $N = 5{,}000$ iterations (`DEFAULT_N_SIMULATIONS = 5000`):

- **Bootstrap Modes:** Random permutation without replacement (preserves exact trade return distribution) and classical bootstrap with replacement.
- **Drawdown Percentiles:** Calculates 50th (median), 95th, and 99th percentile maximum drawdowns.
- **Risk of Ruin:** Evaluates the exact probability that an equity drawdown exceeds the ruin limit ($-30\%$ of starting capital).
- **Consecutive Loss Streaks:** Computes maximum probable losing streaks at a $99\%$ confidence interval.

---

## 4. Long-Period Out-of-Sample Testing (`run_long_forward_validation.py`)

Evaluates strategies over 5+ years of multi-regime historical data:
- **Max Annual Drawdown:** Must never exceed $15\%$ in any individual calendar year.
- **Consistency:** Positive statistical expectancy in $\ge 80\%$ of rolling 6-month windows.
- **Friction Tolerance:** Retains profitability under a $\pm 20\%$ spread/slippage stress penalty.
