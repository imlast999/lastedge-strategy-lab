# LastEdge Strategy Lab — CI/CD Pipeline Specification

> **Module:** `LastEdge Strategy Lab`  
> **Workflow:** `.github/workflows/ci.yml`  
> **Status:** CI ENABLED | CD NOT ENABLED  

---

## 1. Workflow Overview

The Continuous Integration (CI) pipeline validates scientific research models, Walk Forward Analysis, Monte Carlo simulations, exit research variants, and strategy promotion mechanics on every push and pull request to `main`.

- **CI Status Badge**: `[![Strategy Lab CI](https://github.com/imlast999/lastedge-strategy-lab/actions/workflows/ci.yml/badge.svg)](https://github.com/imlast999/lastedge-strategy-lab/actions/workflows/ci.yml)`

---

## 2. Triggers & Permissions

- **Triggers**:
  - `push` to `main`
  - `pull_request` to `main`
- **Permissions**:
  - `contents: read` (Strict least-privilege security)
- **Timeout**: 10 minutes maximum execution limit.

---

## 3. Pipeline Stages & Checks

1. **Environment Setup**:
   - Runner: `ubuntu-latest`
   - Python matrix: `3.10`, `3.11`, `3.12` via `actions/setup-python@v5` with pip caching.
2. **Dependency Installation**:
   - `pip install -r requirements.txt` (`pandas`, `numpy`, `scipy`, `pytest`).
3. **Static Syntax & Compilation Validation**:
   - `python -m compileall core services strategies tests`
4. **Strategy Contract & Promotion Verification**:
   - Direct verification that `BaseStrategy`, `StrategyMetadata`, and `StrategyPromotionService` import cleanly.
5. **Automated Test Suite**:
   - `pytest tests/ -v --tb=short` (25/25 quantitative unit tests and exit research suites).

---

## 4. External Dependencies & Secrets

- **No MT5 Required**: Strategy Lab operates 100% offline (`MT5_OFFLINE_MODE=1`).
- **No Secrets Required**: Zero credentials or tokens are needed.

---

## 5. Local / CI Parity

```bash
# 1. Compile check
python -m compileall core services strategies tests

# 2. Strategy contract & promotion check
python -c "from strategies.base import BaseStrategy, StrategyMetadata; from services.promotion import StrategyPromotionService; print('OK')"

# 3. Run test suite
pytest tests/ -v
```

---

## 6. Continuous Deployment (CD)

> [!NOTE]
> Automatic Deployment is **NOT ENABLED**. Promoted strategies are reviewed and exported to `Trading Engine` through verified promotion runs.
