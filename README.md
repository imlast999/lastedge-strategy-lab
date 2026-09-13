<div align="center">

<img src="branding/LastEdge_Banner.png" alt="LastEdge Strategy Lab Banner" width="100%">

# LastEdge Strategy Lab

[![Strategy Lab CI](https://github.com/imlast999/lastedge-strategy-lab/actions/workflows/ci.yml/badge.svg)](https://github.com/imlast999/lastedge-strategy-lab/actions/workflows/ci.yml)

> **Repository:** [`imlast999/lastedge-strategy-lab`](https://github.com/imlast999/lastedge-strategy-lab)  
> **Role:** Quantitative Research Laboratory, Historical Data Pipeline, WFA & Strategy Promotion  
> **Status:** Production Ready  
> **Tests:** 46 / 46 Passed (100% Green)  

</div>

---

## 1. Overview

**LastEdge Strategy Lab** is the scientific and quantitative research engine of the LastEdge platform. It empowers quantitative researchers to design, backtest, optimize, stress-test, and promote algorithmic trading strategies using empirical mathematical models.

### Key Capabilities:
- **Unified Research Pipeline CLI**: Single-command orchestrator for Backtesting, Exit Research, WFA, Monte Carlo, and Promotion (`run_pipeline.py`).
- **Historical Data Store**: Offline Parquet & CSV dataset loading and validation (`services/data_loader.py`).
- **Realistic Backtesting**: Tick and bar simulations modeling spread, commissions, and slippage (`core/trade_costs.py`).
- **Walk Forward Analysis (WFA)**: Multi-window rolling optimization with out-of-sample stability scoring (`core/walkforward.py`).
- **Monte Carlo Engine**: Statistical resimulation for maximum drawdown and risk-of-ruin probability at 95% and 99% confidence levels (`core/montecarlo.py`).
- **Exit Research Framework**: Independent exit rule optimization (partial exits, ATR trailing, dynamic breakeven).
- **Candidate Promotion Pipeline**: Automated candidate registration, configuration freezing, SHA-256 code hashing, and cryptographic packaging for `Trading Engine` (`services/promotion.py`).
- **Typed Signal Contract**: Canonical implementation of [`SignalIntent`](strategies/base.py) with bit-for-bit parity with Trading Engine.
- **Research REST API**: Local HTTP server on port `8082` for research experiments and candidate listing.
- **Platform Independence**: Runs in offline mode on Windows, macOS, and Linux without requiring MetaTrader 5 installed.

---

## 2. Ecosystem & Sister Repositories

LastEdge is designed as a tri-system decoupled architecture. Strategy Lab operates autonomously in research and data processing while providing verified trading algorithms to the ecosystem:

| Repository | Role | Integration Point |
| :--- | :--- | :--- |
| ⚡ [**LastEdge Trading Engine**](https://github.com/imlast999/lastedge-trading-engine) | MT5 Execution & Risk Engine v2 | **Candidate Ingestion**: Once strategies pass quantitative validation gates (WFA WES $\ge 0.60$, Monte Carlo Ruin $\le 5\%$), Strategy Lab exports verified packages (`.py` + `.json` sidecars with `code_sha256` and `config_hash`) directly into Trading Engine's `strategies/` directory for live execution. |
| 📱 [**LastEdge App**](https://github.com/imlast999/lastedge-app) | Web Dashboard, Mobile & Bots | **Research Telemetry & Control**: LastEdge App queries Strategy Lab's REST API (`http://localhost:8082`) to display backtest results, active research candidates, and trigger pipeline runs remotely. |

Both Strategy Lab and the Trading Engine adhere strictly to the shared [`strategies/base.py`](strategies/base.py) contract with typed `SignalIntent` specifications.

---

## 3. Architecture & Directory Structure

```text
LastEdge Strategy Lab/
├── run_pipeline.py                 # Unified end-to-end research orchestrator CLI
├── run_validation.py               # Multi-level screening and validation pipeline
├── run_long_forward_validation.py  # Multi-year longevity validator
├── run_exit_research.py            # Exit strategy optimization runner
├── rules_config.json               # Research baseline parameters
├── core/
│   ├── walkforward.py              # Walk Forward Analysis (WFA) engine
│   ├── montecarlo.py               # Monte Carlo stress simulation engine
│   ├── trade_costs.py              # Spread, commission & slippage modeling
│   ├── replay_engine.py            # Bar-by-bar backtest simulation engine
│   ├── filters.py                  # Volatility & regime market filters
│   ├── scoring.py                  # Multi-metric robustness scoring
│   └── exit_research/              # Exit strategy research framework
├── data/
│   ├── historical/                 # Canonical historical datasets (Parquet/CSV)
│   ├── candidates/                 # Frozen promoted strategy manifests (.json)
│   └── research.db                 # SQLite research database
├── services/
│   ├── api_server.py               # REST API server (port 8082)
│   ├── data_loader.py              # Historical DataLoader & dataset validation
│   ├── database.py                 # SQLite database manager (research.db)
│   ├── research_store.py           # Experiment & candidate persistence
│   ├── promotion.py                # StrategyPromotionService (SHA-256 packaging)
│   └── long_forward_validation.py  # Out-of-sample long period validator
├── strategies/
│   ├── base.py                     # Canonical BaseStrategy & SignalIntent contract
│   ├── eurusd.py                   # EURUSD candidate model
│   ├── xauusd.py                   # XAUUSD candidate model
│   ├── btceur_new.py               # BTCEUR candidate model
│   └── experimental/               # Sandbox experimental prototypes
├── tests/                          # 46 automated quantitative test suites
└── docs/                           # Technical documentation
```

---

## 4. Quick Start & Installation

### Requirements:
- Python 3.10+ (Windows, macOS, Linux)
- `pandas`, `numpy`, `scipy`, `matplotlib`, `pyarrow`

### Step 1: Install Dependencies
```bash
pip install -r requirements.txt
```

### Step 2: Configure Environment
```bash
cp .env.example .env
```
Default configuration runs in offline mode without MT5:
```ini
MT5_OFFLINE_MODE=1
RESEARCH_API_PORT=8082
RESEARCH_DB_PATH=data/research.db
HISTORICAL_DATA_DIR=data/historical
```

### Step 3: Run Research Pipeline
```bash
# Execute full research pipeline on EURUSD (offline via DataLoader)
python run_pipeline.py --symbol EURUSD --strategy eurusd_simple --bars 20000

# Execute pipeline and automatically promote candidate to Trading Engine
python run_pipeline.py --symbol XAUUSD --strategy xauusd_simple --promote
```
To run the REST API server:
```bash
python -m services.api_server 8082
```

---

## 5. Running Tests & Continuous Integration

```bash
# Run all Strategy Lab quantitative tests locally
python -m pytest tests/ -v
```
Current test suite status: **46 / 46 passed (100% Green)**.

### CI / Continuous Integration:
- **Pipeline**: Automated on every push and pull request to `main` via [GitHub Actions](.github/workflows/ci.yml).
- **Environment**: Multi-Python matrix (3.10, 3.11, 3.12, 3.13) on Ubuntu and Windows.
- **Deterministic & Offline**: Operates in pure offline research mode without external service dependencies.

---

## 6. Documentation Index

For in-depth guides, refer to [`docs/`](docs/):

- 🏛️ [**Architecture**](docs/ARCHITECTURE.md): Research engine design and module boundaries.
- ⚙️ [**Installation**](docs/INSTALLATION.md): Setup on Linux, macOS, and Windows.
- 🔧 [**Configuration**](docs/CONFIGURATION.md): `.env`, `rules_config.json`, and database paths.
- 📂 [**Historical Data Pipeline**](docs/DATA_PIPELINE.md): Parquet/CSV dataset loading, validation, and SHA-256 metadata.
- 🔬 [**Research Pipeline**](docs/RESEARCH.md): Scientific workflow, realistic backtesting, optimization scoring, and exit research.
- 🛡️ [**Validation & Stress Testing**](docs/VALIDATION.md): Walk Forward Analysis (WFA), Monte Carlo simulation, and multi-year longevity.
- 📜 [**Strategy Contract**](docs/STRATEGY_CONTRACT.md): Canonical BaseStrategy definition, `SignalIntent`, and authoring guide.
- 🚀 [**Strategy Promotion**](docs/PROMOTION.md): Promotion lifecycle, security gates, triplet hashes, and production export.
- 🧪 [**Testing & CI/CD**](docs/TESTING.md): Test execution, suite inventory, and GitHub Actions specification.
