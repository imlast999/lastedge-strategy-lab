# LastEdge Strategy Lab — Architecture & Subsystems

> **Module:** `LastEdge Strategy Lab`  
> **Role:** Quantitative Research, Model Validation & Promotion Pipeline  

---

## 1. System Overview

`LastEdge Strategy Lab` provides a scientific framework for strategy development, eliminating curve-fitting through rolling Walk Forward Analysis, Monte Carlo reshuffling, and transaction cost modeling.

```text
               ┌──────────────────────────────┐
               │    Historical Data Store     │
               │   (CSV / Parquet / SQLite)   │
               └──────────────┬───────────────┘
                              │
               ┌──────────────▼───────────────┐
               │     core/replay_engine.py    │
               │  (Spread, Commission, Slip)  │
               └──────────────┬───────────────┘
                              │
  ┌───────────────────────────┼───────────────────────────┐
  │                           │                           │
  ▼                           ▼                           ▼
┌──────────────────┐ ┌──────────────────┐ ┌──────────────────┐
│  Walk Forward    │ │   Monte Carlo    │ │  Exit Research   │
│  (core/walkfwd)  │ │ (core/montecarlo)│ │ (exit_research/) │
└─────────┬────────┘ └────────┬─────────┘ └────────┬─────────┘
          │                   │                    │
          └─────────► ┌───────▼────────┐ ◄─────────┘
                      │  Scoring & WFA │
                      │  Robustness OK │
                      └───────┬────────┘
                              │
                      ┌───────▼────────┐
                      │  Promotion &   │
                      │  SHA-256 Code  │
                      │  Verification  │
                      └───────┬────────┘
                              │
                      ┌───────▼────────┐
                      │ REST API :8082 │
                      └────────────────┘
```

---

## 2. Core Modules Breakdown

### 2.1 Backtesting & Cost Simulation
- **`core/replay_engine.py`**: Bar-by-bar vectorized/iterative simulation engine.
- **`core/trade_costs.py`**: Realistic execution cost model simulating spread widening, broker commissions per lot, and slippage distributions.

### 2.2 Quantitative Validation Engines
- **`core/walkforward.py`**: Implements Walk Forward Analysis. Divides history into rolling in-sample optimization windows and out-of-sample test windows to measure WFA Efficiency Score (WES).
- **`core/montecarlo.py`**: Reshuffles trade returns across 1,000+ simulation paths to estimate max drawdown distributions and risk-of-ruin probability at 95% and 99% confidence levels.
- **`core/exit_research/`**: Tests separate exit strategies (ATR trailing, partial closes, breakeven thresholds) on identical entry signals to optimize expectancy.

### 2.3 Persistence & Promotion
- **`services/database.py`**: SQLite database manager for `data/research.db` in WAL mode.
- **`services/research_store.py`**: CRUD layer for experiment logs, metrics, WFA results, and candidate registries.
- **`services/promotion.py`**: `StrategyPromotionService` freezes parameters, generates `config_hash` and `code_sha256`, and packages approved candidates for deployment into `Trading Engine`.

### 2.4 Research REST API
- **`services/api_server.py`**: HTTP server on port `8082` providing endpoints for experiments, candidates, and promotion triggers.
