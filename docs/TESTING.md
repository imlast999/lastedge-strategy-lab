# LastEdge Strategy Lab — Testing Guide

> **Module:** `LastEdge Strategy Lab`  
> **Framework:** `pytest`  
> **Current Status:** 25 / 25 Passed (100% Green)  

---

## 1. Running Test Suites

```powershell
# Run all Strategy Lab quantitative tests
python -m pytest tests/

# Run with verbose output
python -m pytest tests/ -v

# Run exit research tests specifically
python -m pytest tests/exit_research/ -v
```

---

## 2. Test Coverage Inventory

| Test Module | Tests | Focus Area |
|---|:---:|---|
| `tests/exit_research/test_runner_examples.py` | 5 | Exit simulation runner, trade cost deductions |
| `tests/exit_research/test_variants_examples.py`| 1 | Trailing stop, partial exit, and breakeven logic |
| `tests/test_api_server.py` | 1 | Research REST API endpoints (:8082) |
| `tests/test_p53_long_forward_validation.py` | 6 | Multi-year window rolling and longevity metrics |
| `tests/test_promotion.py` | 1 | Candidate registration, config hashing, SHA-256 verification |
| `tests/test_research_store.py` | 4 | SQLite research database CRUD operations |
| `tests/test_xauusd_gsrs_strategy.py` | 7 | GSRS strategy indicator calculations and entry setup |
