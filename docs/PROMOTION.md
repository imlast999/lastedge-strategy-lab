# LastEdge Strategy Lab — Strategy Promotion Pipeline

> **Module:** `LastEdge Strategy Lab`  
> **Source File:** `services/promotion.py`  

---

## 1. Promotion Lifecycle

```text
EXPERIMENTAL -> BACKTESTED -> OPTIMIZED -> VALIDATED -> CANDIDATE -> APPROVED -> PRODUCTION
```

---

## 2. Integrity Hashing & Verification

When a candidate strategy is registered and approved via `StrategyPromotionService`:

1. **Config Hash**: SHA-256 hash of the normalized JSON configuration (`config_hash`).
2. **Code Hash**: SHA-256 hash of the raw Python source code file (`code_sha256`).
3. **Export Package**: The strategy file is copied to `Trading Engine/strategies/<symbol>_v<version>.py` and its destination SHA-256 is verified to match `code_sha256` exactly.
