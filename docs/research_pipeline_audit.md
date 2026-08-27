# LastEdge Strategy Lab — Quantitative Research Pipeline Audit

> **Document:** `docs/research_pipeline_audit.md`  
> **Date:** 2026-08-27  
> **Phase:** Phase 7 — Strategy Lab Research Pipeline Audit  
> **Repository:** `imlast999/lastedge-strategy-lab`  
> **Status:** AUDIT COMPLETE (Zero Source Code Modified)  

---

## 1. Executive Summary

This audit presents an empirical, code-level analysis of the quantitative research, validation, and promotion pipeline within **LastEdge Strategy Lab**.

The audit evaluates:
1. The real operational lifecycle from strategy hypothesis to production export.
2. The integrity and uniformity of the `BaseStrategy` / `StrategyMetadata` contract.
3. The underlying engines for backtesting, WFA, Monte Carlo, and exit optimization.
4. The exact entrypoints, database models, REST APIs, and critical architectural gaps.

---

## 2. Current Strategy Lifecycle

The actual implementation status of each stage in the strategy lifecycle:

```text
1. Strategy Creation        [ MANUAL ]          (Write class in strategies/experimental/)
       │
       ▼
2. Baseline Backtesting     [ AUTOMATED ]       (core/replay_engine.py with spread, slip, commission)
       │
       ▼
3. Exit Research Variants   [ AUTOMATED ]       (core/exit_research/: Trailing, Partial, Breakeven)
       │
       ▼
4. Walk Forward Analysis    [ AUTOMATED ]       (core/walkforward.py: 4,320 train / 720 test / 720 step)
       │
       ▼
5. Monte Carlo Simulation   [ AUTOMATED ]       (core/montecarlo.py: 5,000 iterations, 99% CI)
       │
       ▼
6. Candidate Registration   [ PROGRAMMATIC ]    (services/promotion.py: config_hash & code_sha256)
       │
       ▼
7. Promotion Approval       [ PROGRAMMATIC/API] (services/promotion.py -> exports to Engine/strategies/)
```

| Lifecycle Stage | Implementation Status | Execution Mode | Primary Module | Inputs | Outputs |
|---|:---:|:---:|---|---|---|
| **1. Strategy Creation** | **EXISTS** | Manual | `strategies/experimental/` | Domain logic, indicators | Python file inheriting `BaseStrategy` |
| **2. Registration** | **EXISTS** | Programmatic / REST | `services/promotion.py` | Strategy file, config dict | `data/candidates/<id>.json` + hashes |
| **3. Backtesting** | **EXISTS** | Automated | `core/replay_engine.py` | OHLCV DataFrame, Strategy | `ReplayStatistics`, trade list |
| **4. Optimization** | **EXISTS** | Script / Grid | `core/scoring.py` | Parameter grid | Multi-metric Fitness Score |
| **5. Retesting** | **EXISTS** | Automated | `run_validation.py` | 10k, 15k, 20k bars | Level degradation tables |
| **6. Walk Forward** | **EXISTS** | Automated | `core/walkforward.py` | Rolling windows | `WFAEfficiencyScore` (WES >= 0.60) |
| **7. Monte Carlo** | **EXISTS** | Automated | `core/montecarlo.py` | Trade list (N=5,000) | Drawdown percentiles (p5..p99), Ruin% |
| **8. Exit Research** | **EXISTS** | Automated | `core/exit_research/` | Entry signal + Exit variants | `ExitResearchReport` + Stability Score |
| **9. Validation** | **EXISTS** | Automated | `services/long_forward_validation.py` | Multi-year sessions | Longevity score (0-100), memory & stress |
| **10. Promotion** | **EXISTS** | Programmatic / REST | `services/promotion.py` | Candidate ID, target Engine path | Verified production package (.py) |

---

## 3. Strategy Contract & Uniformity

The contract defined in `strategies/base.py` is the single source of truth across Strategy Lab and Trading Engine:

```python
@dataclass
class StrategyMetadata:
    required_history: int       # Minimum warmup bars
    symbol: str                 # Trading symbol (EURUSD, XAUUSD, BTCEUR)
    timeframe: str              # Timeframe string (H1, M15)
    strategy_name: str          # Canonical strategy identifier
    version: str                # Semantic version (e.g. 1.0.0)

class BaseStrategy(ABC):
    @property
    @abstractmethod
    def metadata(self) -> StrategyMetadata: ...
    @abstractmethod
    def _get_default_config(self) -> Dict[str, Any]: ...
    @abstractmethod
    def _add_specific_indicators(self, df: pd.DataFrame, config: Dict[str, Any]) -> pd.DataFrame: ...
    @abstractmethod
    def detect_setup(self, df: pd.DataFrame, config: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]: ...
```

### Contract Uniformity Audit:
- **`strategies/eurusd.py`**: Inherits `BaseStrategy` directly (`version='2.0'`).
- **`strategies/xauusd.py`**: Inherits `BaseStrategy` directly (`version='1.0'`).
- **`strategies/btceur_new.py`**: Inherits `BaseStrategy` directly (`version='1.0'`).
- **`strategies/experimental/gold_newstrat/gsrs_strategy.py`**: Implements `GSRSAdapter` inheriting `BaseStrategy` directly (`version='1.0-experimental'`).
- **Verdict**: **100% Contract Conformity**.

---

## 4. Strategy Directory Architecture

The physical filesystem structure in Strategy Lab:

```text
LastEdge Strategy Lab/strategies/
├── __init__.py
├── base.py                             # Abstract BaseStrategy & StrategyMetadata
├── eurusd.py                           # EURUSD simple trend pullback model
├── xauusd.py                           # XAUUSD session momentum model
├── btceur_new.py                       # BTCEUR trend & volatility model
├── btceur_partial.py                   # BTCEUR with partial take profit
├── xauusd_partial.py                   # XAUUSD with partial take profit
└── experimental/
    ├── __init__.py
    ├── eurusd_asian_breakout.py        # Asian range breakout prototype
    ├── eurusd_mtf.py                   # Multi-timeframe trend prototype
    ├── xauusd_psychological.py         # Round numbers & liquidity prototype
    └── gold_newstrat/
        ├── __init__.py
        └── gsrs_strategy.py            # Gold Session Reversal Strategy (GSRS)
```

---

## 5. Research Entrypoints & Workflow

### How to enter a new strategy into Research:
1. **Creation**: Create `strategies/experimental/<name>.py` implementing `BaseStrategy`.
2. **Execute Exit Research & Optimization**:
   ```bash
   python run_exit_research.py --symbol EURUSD --bars 20000
   ```
3. **Execute Multi-Window Validation**:
   ```bash
   python run_validation.py --variants partial_close
   ```
4. **Register & Promote to Production**:
   - Via Python:
     ```python
     from services.promotion import get_promotion_service
     svc = get_promotion_service()
     cand = svc.register_candidate(...)
     svc.promote_to_production(cand["candidate_id"], target_engine_dir=Path("../LastEdge Trading Engine"))
     ```
   - Via REST API (`POST http://localhost:8082/api/research/promote`):
     ```json
     {"candidate_id": "eurusd_simple_2_0_0", "approver": "Architect"}
     ```

---

## 6. Subsystem Deep Dive

### 6.1 Backtesting (`core/replay_engine.py`, `core/trade_costs.py`)
- Models realistic trade frictions on every trade:
  - Half-spread on entry and exit.
  - Round-turn broker commission ($6/lot default).
  - Stochastic / volatility-adjusted slippage.
- Evaluates signals bar-by-bar using warmup buffer (`required_history`).

### 6.2 Optimization & Scoring (`core/scoring.py`)
- Multi-variable fitness function:
  $$\text{Fitness Score} = \text{Sharpe} \times \text{Profit Factor} \times (1 - \text{Max DD}) \times \ln(\text{Trades})$$
- Penalizes overfitting and low trade counts.

### 6.3 Walk Forward Analysis (`core/walkforward.py`)
- Standard Windowing: 4,320 bars Train (~6 months H1), 720 bars Test (~1 month H1), 720 bars Step.
- Computes Walk Forward Efficiency Score (WES):
  $$\text{WES} = \frac{\text{Test Net Pips}}{\text{Train Net Pips}} \times \frac{\text{Test Win Rate}}{\text{Train Win Rate}}$$

### 6.4 Monte Carlo Engine (`core/montecarlo.py`)
- Native Default: $N = 5{,}000$ bootstrap iterations without replacement.
- Outputs: Percentiles $p5, p25, p50, p75, p95, p99$, risk of ruin at $-30\%$, max consecutive losses.

### 6.5 Exit Research Framework (`core/exit_research/`)
- Decouples entries from exits.
- Evaluates 4 baseline variants: Fixed R:R, ATR Trailing, Partial Take Profit, Dynamic Breakeven.
- Exports comprehensive Markdown and CSV run logs to `backtest_results/exit_research/<run_id>/`.

---

## 7. Objective Validation Thresholds

| Metric | Target Threshold | Required? | Source Module |
|---|:---:|:---:|---|
| **Profit Factor (Out of Sample)** | $\ge 1.35$ | YES | `core/scoring.py` |
| **Sharpe Ratio (Annualized)** | $\ge 1.20$ | YES | `core/exit_research/metrics.py` |
| **Max Drawdown (Monte Carlo 99% CI)** | $\le 15.0\%$ | YES | `core/montecarlo.py` |
| **WFA Efficiency Score (WES)** | $\ge 0.60$ | YES | `core/walkforward.py` |
| **Total Out-of-Sample Trades** | $\ge 150$ | YES | `run_validation.py` |
| **Stability Score** | $\ge 20.0$ (High) | YES | `core/exit_research/metrics.py` |

---

## 8. Strategy Promotion & Packaging (`services/promotion.py`)

- **Config Integrity**: Computes SHA-256 hash of sorted JSON parameters (`config_hash`).
- **Source Code Integrity**: Computes SHA-256 hash of the `.py` source file (`code_sha256`).
- **Export Verification**: Copies file to `Trading Engine/strategies/<symbol>_v<version>.py` and re-calculates destination SHA-256 to ensure exact bit-for-bit integrity.
- **Zero Code Modification**: Source code is copied without altering any AST or token.

---

## 9. Research Database (`data/research.db`)

Managed by `services/research_store.py` in SQLite WAL mode:
- **`research_experiments` table**: Stores `experiment_id`, `title`, `hypothesis`, `symbol`, `strategy`, `timeframe`, `config_json`, `metrics_json`, `best_profit_factor`, `best_winrate`, `best_stability_score`, `best_mc_ruin_pct`, `wf_stability`, `git_commit`, `created_at`.
- **Auto-Ingestion**: Automatically indexes filesystem runs from `backtest_results/exit_research/` into SQLite.

---

## 10. REST API Capabilities (Port `:8082`)

- `GET /api/research/health` — Service health probe.
- `GET /api/research/status` — Total experiments and candidates counter.
- `GET /api/research/experiments` — Paginated list of historical research runs.
- `GET /api/research/candidates` — Registered candidate strategies.
- `POST /api/research/promote` — Approves and packages candidate for production.

---

## 11. Automation Matrix

| Stage | Automation Level | Notes |
|---|:---:|---|
| **Strategy Creation** | `MANUAL` | Requires developer/researcher writing Python class. |
| **Backtesting** | `AUTOMATED` | ReplayEngine runs automatically via runner scripts. |
| **Optimization** | `SEMI-AUTOMATIC` | Parameter grids configured in scripts. |
| **Retest** | `AUTOMATED` | Multi-level (10k/15k/20k) executed by `run_validation.py`. |
| **Walk Forward** | `AUTOMATED` | Rolling window execution in `core/walkforward.py`. |
| **Monte Carlo** | `AUTOMATED` | 5,000 iterations executed in `core/montecarlo.py`. |
| **Exit Research** | `AUTOMATED` | Runner executes all variants and computes Stability Score. |
| **Validation** | `AUTOMATED` | Statistical gates evaluated automatically. |
| **Promotion** | `SEMI-AUTOMATIC` | Initiated via REST API call or script. |

---

## 12. Critical Architectural Gaps

| Gap ID | Description | Severity | Impact |
|---|---|:---:|---|
| **GAP-01** | **No Standard Offline Data Ingestor**: `core/replay_engine.py` and `runner.py` contain fallback attempts to import `services.mt5_client`, which is not part of Strategy Lab. An offline dataset provider (`data/historical/*.parquet` or `.csv`) is needed. | **HIGH** | Standalone executions without injected DataFrames require a local historical data file loader. |
| **GAP-02** | **Obsolete Import in `run_long_forward_validation.py`**: Line 11 imports `services.bot_service` (a Trading Engine module) instead of `services.long_forward_validation.LongForwardValidationService`. | **MEDIUM** | Standalone execution of `run_long_forward_validation.py` CLI fails until updated to use internal service. |
| **GAP-03** | **No Unified Single-Command Pipeline CLI**: Currently researchers run 3 distinct scripts (`run_exit_research.py`, `run_validation.py`, `services/promotion.py`) sequentially. | **LOW** | Streamlining into `python -m core.pipeline --strategy ...` would enhance usability. |
| **GAP-04** | **Single-Threaded WFA/Monte Carlo**: Simulations run sequentially on a single core. | **LOW** | Multiprocessing pool would accelerate multi-symbol sweeps. |

---

## 13. Recommended Next Phase

### Phase 8: Strategy Lab Data Pipeline & Offline Historical Store
1. Implement `services/data_loader.py` to seamlessly load CSV/Parquet data from `data/historical/` with automatic date slicing.
2. Clean obsolete legacy imports in CLI runners (`run_long_forward_validation.py`).
3. Implement a unified end-to-end research CLI (`run_pipeline.py`) chaining Backtest -> WFA -> Monte Carlo -> Exit Research -> Candidate Registration in a single deterministic command.
