# GSRS (Gold Session Reversal Strategy) — Python Specification & Backtest Gap Analysis

**Based on:** Analysis of the original technical video footage (~46s), complete transcription, and frame-by-frame inspection (OCR + pixel detection) — GSRS Research Document v0.2.
**Objective:** Translate verified mechanics into implementable code specifications, and explicitly list prioritized items required before executing a valid statistical backtest.

---

## 0. Document Notation

| Symbol | Meaning |
|---|---|
| 🟢 | Confirmed — ready for direct code implementation |
| 🟡 | High Probability — deduced from context, requires parameter verification |
| 🔴 | Unconfirmed / Unknown — critical gap that must be tested empirically |

---

## 1. Confirmed Strategy Parameters (🟢)

### 1.1 Instrument & Timeframe
- **Symbol:** `XAUUSD` (Spot Gold / USD)
- **Timeframe:** `M15` (15-minute candles)
- **Session Focus:** London Open / New York Open crossover windows

### 1.2 Core Indicators
- **EMA Fast:** 20 periods
- **EMA Slow:** 50 periods
- **RSI:** 14 periods with overbought (70) and oversold (30) levels
- **ATR:** 14 periods for volatility-adjusted stop loss placement

### 1.3 Execution Logic
- **Directional Bias:** Alignment with macro trend or session mean-reversion boundary.
- **Entry Trigger:** Rejection wick at key session highs/lows with RSI divergence confirmation.
- **Risk per Trade:** Capped at 1.00% maximum account risk.
- **Exit Architecture:** 50% partial take-profit at 1.5 ATR with Stop Loss moved to Break-Even.
