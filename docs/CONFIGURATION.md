# LastEdge Strategy Lab — Configuration Guide

> **Module:** `LastEdge Strategy Lab`  
> **Config Files:** `.env`, `rules_config.json`  

---

## 1. Environment Variables (`.env`)

| Variable | Type | Default | Description |
|---|---|---|---|
| `MT5_OFFLINE_MODE` | `int` | `1` | Runs research engine using stored CSV/Parquet data without MT5. |
| `RESEARCH_API_PORT` | `int` | `8082` | Port for the local REST API server. |
| `RESEARCH_API_KEY` | `str` | *None* | Optional secret API key for `X-API-Key` authentication. |
| `RESEARCH_DB_PATH` | `str` | `data/research.db` | Path to SQLite research database. |
| `HISTORICAL_DATA_DIR`| `str` | `data/historical` | Directory storing tick and OHLCV history files. |
| `LOG_LEVEL` | `str` | `INFO` | Logging verbosity (`DEBUG`, `INFO`, `WARNING`, `ERROR`). |

---

## 2. Rules Configuration (`rules_config.json`)

Defines default test costs and benchmark thresholds:

```json
{
  "default_spread_pips": {
    "EURUSD": 1.2,
    "XAUUSD": 25.0,
    "BTCEUR": 120.0
  },
  "commission_per_lot": 6.0,
  "slippage_model": {
    "enabled": true,
    "default_slippage_pips": 0.5
  },
  "wfa_defaults": {
    "in_sample_pct": 0.70,
    "windows_count": 5,
    "min_trades_per_window": 30
  },
  "monte_carlo_defaults": {
    "iterations": 1000,
    "confidence_level": 0.99
  }
}
```

---

## 3. Backtest Simulation Horizon Standards (`bars`)

* **Default Public Standard:** **`10,000 bars`** in H1 (~1.7 years of continuous historical market data).
* **Storage Footprint:** Less than **1.5 MB** in Apache Parquet for all 3 primary symbols combined. Recommended disk headroom: **1.0 GB** for logs, database, and HTML artifacts.
* **Custom Horizon Override:** The public repo default remains strictly pinned at 10,000 bars. Users with extended storage or compute can override this parameter directly via CLI (`--bars 30000`), REST API payload (`{"bars": 30000}`), or Python service calls (`run_backtest(..., bars=30000)`). See [DATA_PIPELINE.md](DATA_PIPELINE.md) for full examples.
