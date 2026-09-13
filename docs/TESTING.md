# LastEdge Strategy Lab — Testing & CI/CD Specification

> **Module:** `LastEdge Strategy Lab`  
> **Framework:** `pytest`  
> **Workflow:** `.github/workflows/ci.yml`  
> **Test Status:** 36 / 36 Passed (100% Green)  

---

## 1. Running Automated Tests

```powershell
# Run all 36 Strategy Lab quantitative test suites
python -m pytest tests/

# Run with detailed verbose output
python -m pytest tests/ -v

# Run exit research specific tests
python -m pytest tests/exit_research/ -v

# Run data pipeline and promotion tests
python -m pytest tests/test_data_loader.py tests/test_promotion.py tests/test_end_to_end_research.py -v
```

---

## 2. Test Suite Inventory

| Test Module | Tests | Description |
|---|:---:|---|
| `tests/exit_research/test_runner_examples.py` | 5 | Exit simulation runner, trade cost deductions |
| `tests/exit_research/test_variants_examples.py`| 1 | Trailing stop, partial exit, and breakeven logic |
| `tests/test_api_server.py` | 1 | Research REST API endpoints (:8082) |
| `tests/test_data_loader.py` | 5 | Parquet/CSV loading, deduplication, sorting, validation |
| `tests/test_end_to_end_research.py` | 1 | End-to-end research to promotion integration test |
| `tests/test_p53_long_forward_validation.py` | 6 | Multi-year window rolling and longevity metrics |
| `tests/test_promotion.py` | 5 | Security gates (Cases A-E), tamper detection, hashing |
| `tests/test_research_store.py` | 4 | SQLite research database CRUD operations |
| `tests/test_run_pipeline.py` | 1 | Unified CLI orchestrator execution test |
| `tests/test_xauusd_gsrs_strategy.py` | 7 | GSRS strategy indicator calculations and entry setups |
| **Total** | **36** | **100% Automated Test Coverage** |

---

## 3. GitHub Actions Continuous Integration (`.github/workflows/ci.yml`)

The CI workflow triggers on every push and pull request to `main`:
- **Python Matrix:** Tests across Python `3.10`, `3.11`, `3.12`, `3.13`.
- **Operating Systems:** `ubuntu-latest` and `windows-latest`.
- **Environment:** Offline mode enabled (`MT5_OFFLINE_MODE=1`). No external broker dependencies required.
