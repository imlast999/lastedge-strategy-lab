# Historical Data Pipeline & Offline Storage Architecture

> **Module:** `LastEdge Strategy Lab`  
> **Document:** `docs/DATA_PIPELINE.md`  
> **Status:** Production Standard  

---

## 1. Overview & Purpose

The **LastEdge Strategy Lab Data Pipeline** provides a deterministic, offline data storage and ingestion framework for quantitative trading research. It decouples research experiments, backtests, parameter sweeps, and Walk Forward optimizations from external broker terminals (MetaTrader 5).

---

## 2. Canonical Historical Storage Standard

Historical datasets are stored in `data/historical/` organized hierarchically by symbol and timeframe:

```text
data/
└── historical/
    ├── EURUSD/
    │   ├── H1.parquet            # Primary canonical format (compressed column-store)
    │   ├── H1_metadata.json      # Dataset sidecar metadata (SHA-256, date ranges, bars)
    │   ├── M15.parquet
    │   └── M1.parquet
    ├── XAUUSD/
    │   ├── H1.parquet
    │   └── M15.parquet
    └── BTCEUR/
        ├── H1.parquet
        └── D1.parquet
```

### Supported Formats:
1. **Apache Parquet (`.parquet`)**: High-performance, columnar binary format with snappy/gzip compression. Primary choice for research speed.
2. **CSV (`.csv`)**: Human-readable text format. Supported for manual imports and legacy interop.

---

## 3. Canonical Schema & Column Specifications

Every dataset ingested or loaded by `DataLoader` conforms strictly to the following 6-column canonical structure:

| Column | Data Type | Constraint | Description |
|---|---|---|---|
| `time` | `datetime64[ns, UTC]` | Strictly ascending, unique | Candle open timestamp in UTC |
| `open` | `float64` | $> 0.0$ | Open price |
| `high` | `float64` | $\ge \text{low}, \ge \text{open}, \ge \text{close}$ | High price |
| `low` | `float64` | $\le \text{high}, \le \text{open}, \le \text{close}$ | Low price |
| `close` | `float64` | $> 0.0$ | Close price |
| `volume` | `float64` | $\ge 0.0$ | Tick or real trade volume |
| `spread` | `float64` | Optional, $\ge 0.0$ | Historical spread in points |

---

## 4. `DataLoader` Service API (`services/data_loader.py`)

The `DataLoader` class provides a unified interface for accessing and saving historical datasets:

```python
from services.data_loader import get_data_loader

loader = get_data_loader()

# 1. Load historical dataset with automatic slicing
df, metadata = loader.load(symbol="EURUSD", timeframe="H1", bars=20000)

# 2. Load from specific file
df, metadata = loader.load_from_file("path/to/my_data.parquet", symbol="EURUSD", timeframe="H1")

# 3. Save & normalize dataset with metadata generation
metadata = loader.save_dataset(df, symbol="EURUSD", timeframe="H1", file_format="parquet")

# 4. List all available local datasets
available = loader.list_available_datasets()
```

### Automated Dataset Validation:
- **Deduplication:** Duplicated timestamps are logged and pruned automatically (keeping the most recent observation).
- **Sorting:** Rows are strictly sorted chronologically ascending.
- **Sanity Checks:** Enforces strict positive prices and $High \ge Low$ geometry constraints.

---

## 5. Dataset Metadata & Reproducibility

Every dataset generates a cryptographic SHA-256 hash stored in `DatasetMetadata`:

```json
{
  "symbol": "EURUSD",
  "timeframe": "H1",
  "start_date": "2024-01-01T00:00:00+00:00",
  "end_date": "2026-08-01T00:00:00+00:00",
  "bars_count": 20000,
  "file_path": "/path/to/EURUSD/H1.parquet",
  "file_format": "parquet",
  "file_hash_sha256": "71dddc57d20936d3...",
  "columns": ["time", "open", "high", "low", "close", "volume"],
  "created_at": "2026-08-27T18:00:00Z"
}
```

This SHA-256 hash is recorded in `data/research.db` alongside the strategy code SHA-256 hash and parameter configuration hash to guarantee 100% scientific reproducibility.

---

## 7. Canonical Benchmark Standard: 10,000 Bars

LastEdge Strategy Lab establishes **10,000 continuous H1 candles (~1.7 years of continuous market history)** as the **canonical institutional benchmark standard** across the entire public codebase.

### Storage & System Requirements (10,000 Bars Standard):
* **Dataset Footprint:** Thanks to columnar Apache Parquet compression (`snappy`), a 10,000-candle dataset occupies only **~300 KB – 500 KB per symbol** (~1.5 MB total for EURUSD, XAUUSD, and BTCEUR combined).
* **Recommended Free Disk Space:** A minimum of **1.0 GB of free disk space** is recommended on the host system to comfortably store Parquet datasets, SQLite experiment registries (`research.db`), DuckDB analytical indexes, and full HTML/JSON backtest artifacts.

---

## 8. Scaling to Custom Horizons (e.g. 30,000+ Candles)

The default values in the repository (`default_bars = 10000`) are intentionally preserved so that any user cloning the repository can run zero-configuration backtests on lightweight machines without excessive memory or disk pressure.

Users with ample disk space and computational resources wishing to audit multi-year macroeconomic cycles (such as **30,000 H1 candles $\approx$ 3.5 to 5.0 years**) can scale the simulation horizon without modifying core files:

### 1. Via Unified Research CLI (`run_pipeline.py`):
```bash
python run_pipeline.py --symbol EURUSD --strategy eurusd_flow --bars 30000
```

### 2. Via REST API (`POST /api/backtest/run`):
```json
{
  "symbol": "XAUUSD",
  "strategy": "xauusd_asian_london",
  "timeframe": "H1",
  "bars": 30000
}
```

### 3. Via Python Service API (`services/backtest_service.py`):
```python
from services.backtest_service import get_backtest_service

svc = get_backtest_service()
report = svc.run_backtest(
    symbol="BTCEUR",
    strategy_name="btceur_trend_surge",
    timeframe="H1",
    bars=30000  # Default remains 10000
)
```

### 4. Via Exit Research Runner (`core/exit_research/runner.py`):
```python
from core.exit_research.runner import ExitResearchRunner

runner = ExitResearchRunner(
    symbol="EURUSD",
    levels=[5000, 10000, 20000, 30000]  # Custom bar levels
)
report = runner.run_all(bars=30000)
```
