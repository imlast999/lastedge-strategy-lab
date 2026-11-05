# Discarded Strategies

These strategies were evaluated and discarded following the May 2026 grid search optimization.
They are preserved for historical reference and potential future review.

| Strategy | Discard Reason | Best Profit Factor |
|---|---|---|
| `eurusd_mtf` | Maximum PF 0.42 across the entire parameter grid. No edge found in any combination. | 0.42 |
| `xauusd_psychological` | Maximum PF 0.94, fails to achieve break-even. | 0.94 |
| `xauusd_reversal` | 1 signal in 5,000 candles. Excessively restrictive to produce statistical sample. | N/A |

## Reactivating a Strategy

If any model is revisited in the future:
1. Move the strategy file back to `strategies/` or `strategies/vault/`.
2. Re-run parameter optimization and Walk-Forward Analysis (`scripts/run_wfa.py`).
3. Validate contract conformance via `pytest tests/test_strategy_validation.py`.
