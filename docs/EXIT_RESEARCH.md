# LastEdge Strategy Lab — Exit Research Framework

> **Module:** `LastEdge Strategy Lab`  
> **Source Package:** `core/exit_research/`  

---

## 1. Overview & Decoupled Testing

The Exit Research framework decouples entry signal generation from trade exit mechanics, enabling isolated testing of exit rules across identical historical entry points.

```text
[BaseStrategy (get_signal)] ──► [StrategyAdapter] ──► [ExitResearchRunner]
                                                              │
                                 ┌────────────────────────────┼────────────────────────────┐
                                 ▼                            ▼                            ▼
                          [Variant A: Fixed]           [Variant B: Trailing]        [Variant C: Partial]
                          (Fixed R:R 1:2)              (ATR 1.5x Trailing)          (50% TP1 + Trailing)
```

---

## 2. Exit Strategy Variants (`core/exit_research/variants.py`)

- **Fixed Target**: Classic fixed Stop Loss and Take Profit (e.g. 1.5R / 2.0R).
- **Dynamic Breakeven**: Shifts SL to breakeven once price moves $+1.0 \times \text{ATR}$ in profit.
- **ATR Trailing Stop**: Dynamically ratchets Stop Loss along with favorable price movement.
- **Partial Take Profit**: Closes 50% of volume at Target 1 and trails remainder to maximize trend capture.
