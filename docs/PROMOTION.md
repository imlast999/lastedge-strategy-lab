# LastEdge Strategy Lab — Strategy Promotion Pipeline

> **Module:** `LastEdge Strategy Lab`  
> **Source File:** `services/promotion.py`  
> **Status:** Production Standard  

---

## 1. Promotion Lifecycle

```text
EXPERIMENTAL ──► BACKTESTED ──► OPTIMIZED ──► VALIDATED ──► CANDIDATE ──► APPROVED ──► PRODUCTION
```

Promotion from **Research Candidate** to **Production Trading Strategy** is governed by explicit quantitative security gates and bit-for-bit cryptographic verification.

---

## 2. Triplet Integrity Hashes

Every candidate registered in `data/candidates/<candidate_id>.json` locks three cryptographic identities:

1. **Code SHA-256 (`code_sha256`)**: SHA-256 hash of the exact Python strategy module file on disk.
2. **Config Hash (`config_hash`)**: SHA-256 hash of the alphabetically sorted, canonical JSON rules dictionary.
3. **Dataset SHA-256 (`dataset_sha256`)**: SHA-256 hash of the historical data file used during research.

---

## 3. Quantitative Security & Validation Gates

The `--promote` flag in `run_pipeline.py` or a call to `StrategyPromotionService.promote_to_production()` does **NOT** grant automatic approval. It evaluates the following strict gates:

| Gate | Criterion | Action if Failed |
|---|---|---|
| **Gate 1: Pipeline Completion** | Baseline Backtest, WFA, and Monte Carlo must all be executed. | Promotion **BLOCKED** |
| **Gate 2: WFA Stability** | Walk Forward Efficiency Score (WES) $\ge 0.60$ and `passed == True`. | Promotion **BLOCKED** |
| **Gate 3: Monte Carlo Risk** | Probability of Ruin $\le 5.0\%$ and `passed == True`. | Promotion **BLOCKED** |
| **Gate 4: Code Integrity** | Current source file on disk must match registered `code_sha256` bit-for-bit. | Promotion **BLOCKED** |
| **Gate 5: Config Integrity** | Recomputed hash of parameters must match registered `config_hash`. | Promotion **BLOCKED** |
| **Gate 6: Dataset Integrity** | Dataset hash must be present and verified against research records. | Promotion **BLOCKED** |

---

## 4. Production Export Package

Upon passing all gates, `StrategyPromotionService` exports two files to `Trading Engine/strategies/`:
1. `<symbol>_v<version>.py`: Clean Python strategy module.
2. `<symbol>_v<version>.json`: Sidecar manifest containing full metadata, config, hashes, promotion timestamp, and approval signature.
