<div align="center">

<img src="branding/LastEdge_Banner.png" alt="LastEdge Strategy Lab Banner" width="100%">

# LastEdge Strategy Lab

[![Strategy Lab CI](https://github.com/imlast999/lastedge-strategy-lab/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/imlast999/lastedge-strategy-lab/actions/workflows/ci.yml)
[![Tests](https://img.shields.io/badge/Tests-54%2F54%20Passed-success)](https://github.com/imlast999/lastedge-strategy-lab)
[![Pillars](https://img.shields.io/badge/Quantitative%20Pillars-6%20Active-purple)](https://github.com/imlast999/lastedge-strategy-lab)

> **Repository:** [`imlast999/lastedge-strategy-lab`](https://github.com/imlast999/lastedge-strategy-lab)  
> **Role:** Quantitative Research, Backtesting, Walk-Forward Analysis, Monte Carlo & Strategy Promotion  
> **Status:** Production Ready  
> **Tests:** 54 / 54 Passed (100% Green)  

</div>

---

> [!NOTE]
> **Part of the [LastEdge](https://github.com/imlast999/LastEdge) Ecosystem**  
> This repository is the research and strategy engineering core of the **LastEdge** quantitative trading framework. While it can run independently for offline research, **we strongly recommend running the complete LastEdge suite** via the main orchestrator repository ([`imlast999/LastEdge`](https://github.com/imlast999/LastEdge)) using its automated clone script (`setup.bat` / `clone_repos.bat`) to enable synchronized strategy promotion directly into the live Trading Engine.

---

## 1. Overview

**LastEdge Strategy Lab** is the scientific research, simulation, and validation laboratory for algorithmic trading strategies. It enforces an institutional 6-gate quantitative framework ensuring no model reaches live trading without passing rigorous statistical stress testing.

### Key Capabilities:
- **The 6 Quantitative Pillars Suite**: Institutional-grade validation (1,000 Monte Carlo permutations, Walk-Forward Analysis WFE $\ge 60\%$, Deflated Sharpe Ratio against overfitting, Mathematical Payoff, Market Regimes Stress Test, and Cryptographic Promotion).
- **Dynamic Strategy Discovery**: Automatically scans `strategies/`, `strategies/vault/`, and `strategies/private/` to discover and register new strategy files on the fly.
- **Unified Research Pipeline CLI**: Single-command orchestrator for Backtesting, Exit Research, WFA, Monte Carlo, and Promotion (`run_pipeline.py`).
- **Standardized Execution Matrix**: Aligned scoring thresholds (`LOW < 0.60`, `MEDIUM 0.60 - 0.66`, `HIGH 0.67 - 0.84`, `VERY_HIGH >= 0.85`) ensuring simulated performance faithfully reflects live MT5 execution gates.
- **Historical Data Store**: Offline Parquet & CSV dataset loading and validation (`services/data_loader.py`).
- **Realistic Backtesting**: Tick and bar simulations modeling spread, commissions, and slippage (`core/trade_costs.py`).
- **Walk Forward Analysis (WFA)**: Multi-window rolling optimization with out-of-sample stability scoring (`core/walkforward.py`).
- **Monte Carlo Engine**: Statistical resimulation for maximum drawdown and risk-of-ruin probability at 95% and 99% confidence levels (`core/montecarlo.py`).
- **Exit Research Framework**: Independent exit rule optimization (partial exits, ATR trailing, dynamic breakeven).
- **Candidate Promotion Pipeline**: Automated candidate registration, configuration freezing, SHA-256 code hashing, and cryptographic packaging for `Trading Engine` (`services/promotion.py`).
- **Vault Alpha Consolidation**: Multi-pillar audit suite verifying private proprietary strategies against 10,000-candle regimes, weeding out unviable setups to focus computational resources on institutional-grade alpha.
- **Typed Signal Contract**: Canonical implementation of [`SignalIntent`](strategies/base.py) with bit-for-bit parity with Trading Engine.
- **Research REST API**: Local HTTP server on port `8082` for research experiments and candidate listing.
- **Platform Independence**: Runs in offline mode on Windows, macOS, and Linux without requiring MetaTrader 5 installed.

---

## 2. Signal Confidence & Execution Tiers

Strategy Lab simulates execution using the exact same deterministic scoring matrix enforced by the Trading Engine:

| Tier | Confluence Score | Simulation / Live Role | Execution Outcome |
| :--- | :---: | :--- | :--- |
| **`VERY_HIGH`** | **`0.85 – 1.00`** | **Institutional Conviction** | Automated live execution in MT5 with immediate IOC fill. |
| **`HIGH`** | **`0.67 – 0.84`** | **Automated Production** | Automated live execution in MT5 (calibrated $\ge 0.67$ gate). |
| **`MEDIUM`** | **`0.60 – 0.66`** | **Discretionary Validation** | Dispatched to Web Dashboard & Mobile App for 1-click confirmation. |
| **`LOW`** | **`< 0.60`** | **Pre-Filter Suppression** | Completely suppressed. Discarded as market noise to protect capital. |

---

## 3. Ecosystem & Sister Repositories

LastEdge is designed as a tri-system decoupled architecture. Strategy Lab operates autonomously in research and data processing while providing verified trading algorithms to the ecosystem:

| Repository | Role | Integration Point |
| :--- | :--- | :--- |
| 🧭 [**LastEdge (Main Suite)**](https://github.com/imlast999/LastEdge) | Ecosystem Orchestrator & CLI | **Unified Workspace**: Automated setup script (`setup.bat` / `clone_repos.bat`) to synchronize and run the complete three-repository trading suite. |
| ⚡ [**LastEdge Trading Engine**](https://github.com/imlast999/lastedge-trading-engine) | MT5 Execution & Risk Engine v2 | **Candidate Ingestion**: Once strategies pass quantitative validation gates (WFA WES $\ge 0.60$, Monte Carlo Ruin $\le 1\%$), Strategy Lab exports verified packages (`.py` + `.json` sidecars with `code_sha256` and `config_hash`) directly into Trading Engine's `strategies/` directory for live execution. |
| 📱 [**LastEdge App**](https://github.com/imlast999/lastedge-app) | Web Dashboard, Mobile & Bots | **Research Telemetry & Control**: LastEdge App queries Strategy Lab's REST API (`http://localhost:8082`) to display backtest results, active research candidates, and trigger pipeline runs remotely from mobile or web. |

---

## 4. Architecture & Directory Structure

```text
LastEdge Strategy Lab/
├── run_pipeline.py                 # Unified end-to-end research orchestrator CLI
├── rules_config.json               # Baseline candidate parameters and confidence thresholds
├── core/
│   ├── strategy_catalog.py         # Dynamic Strategy Catalog & On-the-Fly Discovery
│   ├── scoring.py                  # Flexible scoring & confirmation evaluation
│   ├── replay_engine.py            # Candle replay backtesting engine
│   ├── walkforward.py              # Walk-Forward Analysis rolling window optimizer
│   ├── montecarlo.py               # 1,000 permutations risk-of-ruin engine
│   └── trade_costs.py              # Realistic slippage & broker spread model
├── strategies/                     # Strategy implementation directory
│   ├── base.py                     # Canonical BaseStrategy & SignalIntent contract
│   ├── eurusd.py, xauusd.py, ...   # Standard baseline models
│   ├── vault/                      # Proprietary strategy vault
│   └── private/                    # Local git-ignored custom strategies
├── services/
│   ├── api_server.py               # REST API Server (:8082)
│   ├── backtest_service.py         # Verbose Reliability Verdict backtest service
│   ├── research_store.py           # SQLite experiment database (experiments.db)
│   └── promotion.py                # Cryptographic strategy promoter
├── tests/                          # 54 automated quantitative & integration tests
└── docs/                           # Research documentation & quant specifications
```

---

## 5. Running Tests & Continuous Integration

```bash
# Run all Strategy Lab tests locally
python -m pytest tests/ -v
```
Current test suite status: **54 / 54 passed (100% Green)**.

### CI / Continuous Integration:
- **Strategy Lab CI**: Automated on every push and pull request via [GitHub Actions](.github/workflows/ci.yml).
- **Environment**: Multi-Python matrix (3.10, 3.11, 3.12, 3.14) on Ubuntu and Windows.

---

## 6. Documentation Index

For in-depth mathematical documentation, refer to [`docs/`](docs/):

- 📐 [**Architecture & Pipeline**](docs/ARCHITECTURE.md): Research pipeline workflows, IPC, and components.
- 🔬 [**The 6 Quantitative Pillars**](docs/PILLARS.md): Mathematical formulations for Monte Carlo, WFA, and DSR.
- 🛡️ [**Strategy Promotion & Security**](docs/PROMOTION.md): Cryptographic sidecar generation and validation.
- 🧪 [**Testing & CI/CD**](docs/TESTING.md): Test suite structure and verification procedures.
