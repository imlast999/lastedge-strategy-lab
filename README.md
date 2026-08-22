# LastEdge Strategy Lab

> **Repository:** `lastedge-strategy-lab`  
> **Role:** Quantitative Research Laboratory, Walk Forward Optimization & Strategy Promotion  
> **Status:** Production Ready  

---

## 1. Overview

**LastEdge Strategy Lab** is the scientific and quantitative engine of the LastEdge platform. It empowers quantitative researchers to design, backtest, optimize, stress-test, and promote algorithmic trading strategies using empirical mathematical models.

### Key Capabilities:
- **Realistic Backtesting**: Tick and bar simulations modeling spread, commissions, and slippage (`core/trade_costs.py`).
- **Walk Forward Analysis (WFA)**: Multi-window rolling optimization with out-of-sample stability scoring (`core/walkforward.py`).
- **Monte Carlo Engine**: Statistical resimulation for maximum drawdown and risk-of-ruin probability at 95% and 99% confidence levels (`core/montecarlo.py`).
- **Exit Research Framework**: Independent exit rule optimization (partial exits, ATR trailing, dynamic breakeven).
- **Candidate Promotion Pipeline**: Automated candidate registration, configuration freezing, SHA-256 code hashing, and packaging for `Trading Engine` (`services/promotion.py`).
- **Research REST API**: Local HTTP server on port `8082` for research experiments and candidate listing.
- **Platform Independence**: Runs in offline mode on Windows, macOS, and Linux without requiring MetaTrader 5 installed.

---

## 2. Architecture & Modules

```text
LastEdge Strategy Lab/
├── run_validation.py               # Main research screening pipeline
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
│       ├── runner.py               # Exit research simulation runner
│       ├── variants.py             # Trailing, partial, breakeven exit rules
│       ├── metrics.py              # Exit efficiency scoring metrics
│       └── strategy_adapter.py     # Strategy harness for exit experiments
├── services/
│   ├── api_server.py               # REST API server (port 8082)
│   ├── database.py                 # SQLite database manager (research.db)
│   ├── research_store.py           # Experiment & candidate persistence
│   ├── promotion.py                # StrategyPromotionService (SHA-256 packaging)
│   └── long_forward_validation.py  # Out-of-sample long period validator
├── strategies/
│   ├── base.py                     # Canonical BaseStrategy & StrategyMetadata contract
│   ├── eurusd.py                   # EURUSD candidate model
│   ├── xauusd.py                   # XAUUSD candidate model
│   ├── btceur_new.py               # BTCEUR candidate model
│   └── experimental/               # Sandbox experimental prototypes
├── tests/                          # 25 automated quantitative test suites
└── docs/                           # Technical documentation
```

---

## 3. Quick Start & Installation

### Requirements:
- Python 3.10+ (Windows, macOS, Linux)
- `pandas`, `numpy`, `scipy`, `matplotlib`

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
```

### Step 3: Run Research Validation
```bash
python run_validation.py
```
To run the REST API server:
```bash
python -m services.api_server 8082
```

---

## 4. Running Tests

```bash
python -m pytest tests/
```
Current test suite status: **25 / 25 passed (100% Green)**.

---

## 5. Documentation Index

For in-depth guides, refer to the documentation in [`docs/`](docs/):

- 🏛️ [**Architecture**](docs/ARCHITECTURE.md): Research engine design and module boundaries.
- ⚙️ [**Installation**](docs/INSTALLATION.md): Setup on Linux, macOS, and Windows.
- 🔧 [**Configuration**](docs/CONFIGURATION.md): `.env`, `rules_config.json`, and database paths.
- 🔬 [**Research Workflow**](docs/RESEARCH.md): The scientific lifecycle from hypothesis to production.
- 📊 [**Backtesting Engine**](docs/BACKTESTING.md): Realistic execution costs and replay mechanics.
- 🎯 [**Optimization**](docs/OPTIMIZATION.md): Parameter grid search and out-of-sample validation.
- 🔄 [**Walk Forward Analysis**](docs/WALK_FORWARD.md): WFA windows, scoring, and overfitting prevention.
- 🎲 [**Monte Carlo Engine**](docs/MONTE_CARLO.md): Risk of ruin, drawdown confidence intervals, and bootstrap tests.
- 🚪 [**Exit Research**](docs/EXIT_RESEARCH.md): Exit rules, partial closures, and ATR trailing optimization.
- 💡 [**Strategy Generation**](docs/STRATEGY_GENERATION.md): Creating compliant candidate strategies.
- 📜 [**Strategy Contract**](docs/STRATEGY_CONTRACT.md): Specification of `BaseStrategy` and metadata.
- 🚀 [**Promotion Pipeline**](docs/PROMOTION.md): Candidate freezing, SHA-256 hashing, and export to Trading Engine.
- 🛡️ [**Validation Framework**](docs/VALIDATION.md): Multi-year longevity tests and robust scoring.
- 🧪 [**Testing Guide**](docs/TESTING.md): Quantitative unit tests and benchmark suites.
