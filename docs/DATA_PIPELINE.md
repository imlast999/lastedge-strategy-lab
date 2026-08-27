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

## 6. Offline Execution & Broker Decoupling

When executing research via `run_pipeline.py`, `ReplayEngine`, `WalkForwardTester`, or `ExitResearchRunner`:
1. The engine queries `DataLoader` for the local Parquet or CSV dataset.
2. If found, all simulations run completely offline without opening network sockets or connecting to MetaTrader 5.
3. If not found, MT5 is only queried as an optional live ingestor on Windows systems where MetaTrader 5 is installed.
