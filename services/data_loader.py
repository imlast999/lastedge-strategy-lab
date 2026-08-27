"""
LastEdge Strategy Lab — Historical Data Loader & Storage Service
services/data_loader.py

Provides a standardized, robust interface for loading, validating, and managing
offline historical market datasets (Parquet and CSV) for quantitative research,
backtesting, Walk Forward Analysis, and Exit Research without requiring MetaTrader 5.
"""

from __future__ import annotations

import os
import json
import hashlib
import logging
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Dict, Any, List, Union, Tuple

import pandas as pd
import numpy as np

logger = logging.getLogger(__name__)

# Default historical storage root
_DEFAULT_HISTORICAL_DIR = Path(
    os.getenv(
        "HISTORICAL_DATA_DIR",
        os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "historical")
    )
)

# Canonical column names required for backtest engines
CANONICAL_COLUMNS = ["time", "open", "high", "low", "close", "volume"]


@dataclass
class DatasetMetadata:
    """Metadata describing a historical market dataset."""
    symbol: str
    timeframe: str
    start_date: str
    end_date: str
    bars_count: int
    file_path: str
    file_format: str
    file_hash_sha256: str
    columns: List[str]
    created_at: str

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class DatasetValidationError(ValueError):
    """Raised when a dataset fails structural, chronological, or price sanity checks."""
    pass


class DataLoader:
    """
    Standardized Historical Data Loader for LastEdge Strategy Lab.
    """

    def __init__(self, storage_dir: Optional[Union[str, Path]] = None):
        self.storage_dir = Path(storage_dir) if storage_dir else _DEFAULT_HISTORICAL_DIR
        self.storage_dir.mkdir(parents=True, exist_ok=True)

    def _compute_file_hash(self, file_path: Path) -> str:
        """Computes SHA-256 hash of a historical data file for reproducibility tracking."""
        sha = hashlib.sha256()
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(65536), b""):
                sha.update(chunk)
        return sha.hexdigest()

    def resolve_dataset_path(self, symbol: str, timeframe: str = "H1") -> Optional[Path]:
        """
        Locates the dataset file for a given symbol and timeframe.
        Searches in order:
          1. data/historical/<SYMBOL>/<TIMEFRAME>.parquet
          2. data/historical/<SYMBOL>/<TIMEFRAME>.csv
          3. data/historical/<SYMBOL>_<TIMEFRAME>.parquet
          4. data/historical/<SYMBOL>_<TIMEFRAME>.csv
          5. data/historical/<SYMBOL>.parquet
          6. data/historical/<SYMBOL>.csv
        """
        sym = symbol.upper()
        tf = timeframe.upper()

        candidate_paths = [
            self.storage_dir / sym / f"{tf}.parquet",
            self.storage_dir / sym / f"{tf}.csv",
            self.storage_dir / f"{sym}_{tf}.parquet",
            self.storage_dir / f"{sym}_{tf}.csv",
            self.storage_dir / f"{sym}.parquet",
            self.storage_dir / f"{sym}.csv",
            self.storage_dir / sym.lower() / f"{tf.lower()}.parquet",
            self.storage_dir / sym.lower() / f"{tf.lower()}.csv",
            self.storage_dir / f"{sym.lower()}_{tf.lower()}.parquet",
            self.storage_dir / f"{sym.lower()}_{tf.lower()}.csv",
        ]

        for path in candidate_paths:
            if path.exists() and path.is_file():
                return path

        return None

    def validate_and_normalize(self, df: pd.DataFrame, symbol: str = "UNKNOWN", timeframe: str = "H1") -> pd.DataFrame:
        """
        Validates structure and normalizes raw DataFrame into canonical LastEdge format:
          - Columns: time (datetime UTC), open, high, low, close, volume (all float/numeric)
          - Sorted chronologically ascending
          - Deduplicated timestamps
          - Valid OHLC price constraints (low <= open, close <= high)
        """
        if df is None or len(df) == 0:
            raise DatasetValidationError("Dataset is empty.")

        df = df.copy()

        # Map alternate column names
        col_map = {}
        for col in df.columns:
            c_low = str(col).lower().strip()
            if c_low in ("time", "timestamp", "datetime", "date"):
                col_map[col] = "time"
            elif c_low in ("open", "o"):
                col_map[col] = "open"
            elif c_low in ("high", "h"):
                col_map[col] = "high"
            elif c_low in ("low", "l"):
                col_map[col] = "low"
            elif c_low in ("close", "c"):
                col_map[col] = "close"
            elif c_low in ("volume", "vol", "tick_volume", "v"):
                col_map[col] = "volume"
            elif c_low in ("spread", "sp"):
                col_map[col] = "spread"

        df.rename(columns=col_map, inplace=True)

        # Check required columns
        required = ["time", "open", "high", "low", "close"]
        missing = [r for r in required if r not in df.columns]
        if missing:
            raise DatasetValidationError(f"Missing required price columns: {missing}. Available: {list(df.columns)}")

        # Fill default volume if not present
        if "volume" not in df.columns:
            df["volume"] = 1.0

        # Normalize timestamps
        try:
            df["time"] = pd.to_datetime(df["time"], utc=True)
        except Exception as e:
            raise DatasetValidationError(f"Failed to parse 'time' column into valid datetime: {e}")

        # Check for null timestamps
        if df["time"].isnull().any():
            raise DatasetValidationError("Dataset contains null or unparseable timestamps.")

        # Ensure numeric float conversion
        for num_col in ["open", "high", "low", "close", "volume"]:
            df[num_col] = pd.to_numeric(df[num_col], errors="coerce")
            if df[num_col].isnull().any():
                raise DatasetValidationError(f"Column '{num_col}' contains invalid/null numeric values.")

        # Deduplicate timestamps (keep last)
        duplicates = df.duplicated(subset=["time"]).sum()
        if duplicates > 0:
            logger.warning("[DataLoader] Found %d duplicate timestamps for %s %s. Keeping last observation.", duplicates, symbol, timeframe)
            df = df.drop_duplicates(subset=["time"], keep="last")

        # Sort chronologically ascending
        df = df.sort_values("time").reset_index(drop=True)

        # Validate price integrity
        if (df["open"] <= 0).any() or (df["high"] <= 0).any() or (df["low"] <= 0).any() or (df["close"] <= 0).any():
            raise DatasetValidationError("Price columns must contain strictly positive values (> 0).")

        # Check high >= low constraint
        invalid_hl = (df["high"] < df["low"]).sum()
        if invalid_hl > 0:
            raise DatasetValidationError(f"Found {invalid_hl} rows where High < Low.")

        # Ensure canonical column order
        cols = ["time", "open", "high", "low", "close", "volume"]
        if "spread" in df.columns:
            cols.append("spread")

        # Preserve any additional custom indicator columns
        extra_cols = [c for c in df.columns if c not in cols]
        return df[cols + extra_cols]

    def load_from_file(self, file_path: Union[str, Path], symbol: str = "UNKNOWN", timeframe: str = "H1") -> Tuple[pd.DataFrame, DatasetMetadata]:
        """
        Loads and validates a historical dataset directly from a specific file path.
        """
        p = Path(file_path)
        if not p.exists() or not p.is_file():
            raise FileNotFoundError(f"Historical data file not found: {p}")

        ext = p.suffix.lower()
        if ext == ".parquet":
            df_raw = pd.read_parquet(p)
            fmt = "parquet"
        elif ext in (".csv", ".txt"):
            df_raw = pd.read_csv(p)
            fmt = "csv"
        else:
            raise ValueError(f"Unsupported historical file format '{ext}'. Must be .parquet or .csv.")

        df = self.validate_and_normalize(df_raw, symbol=symbol, timeframe=timeframe)
        file_hash = self._compute_file_hash(p)

        meta = DatasetMetadata(
            symbol=symbol.upper(),
            timeframe=timeframe.upper(),
            start_date=df["time"].iloc[0].isoformat(),
            end_date=df["time"].iloc[-1].isoformat(),
            bars_count=len(df),
            file_path=str(p.resolve()),
            file_format=fmt,
            file_hash_sha256=file_hash,
            columns=list(df.columns),
            created_at=datetime.now(timezone.utc).isoformat(),
        )

        return df, meta

    def load(
        self,
        symbol: str,
        timeframe: str = "H1",
        bars: Optional[int] = None,
        start_date: Optional[Union[str, datetime]] = None,
        end_date: Optional[Union[str, datetime]] = None
    ) -> Tuple[pd.DataFrame, DatasetMetadata]:
        """
        Loads historical dataset for a symbol and timeframe from the local storage.
        Optionally filters by bars count or date range.
        """
        file_path = self.resolve_dataset_path(symbol, timeframe)
        if not file_path:
            raise FileNotFoundError(
                f"No historical dataset found for symbol='{symbol}', timeframe='{timeframe}' in '{self.storage_dir}'. "
                f"Please place {symbol.upper()}_{timeframe.upper()}.parquet or .csv in {self.storage_dir}."
            )

        df, meta = self.load_from_file(file_path, symbol=symbol, timeframe=timeframe)

        # Date range filtering
        if start_date:
            ts_start = pd.to_datetime(start_date, utc=True)
            df = df[df["time"] >= ts_start]

        if end_date:
            ts_end = pd.to_datetime(end_date, utc=True)
            df = df[df["time"] <= ts_end]

        # Bars count limit (take latest N bars if specified)
        if bars is not None and bars > 0 and len(df) > bars:
            df = df.iloc[-bars:].reset_index(drop=True)

        if len(df) == 0:
            raise DatasetValidationError(f"Dataset for {symbol} {timeframe} contains 0 rows after applying filters.")

        # Update metadata for sliced slice
        meta.start_date = df["time"].iloc[0].isoformat()
        meta.end_date = df["time"].iloc[-1].isoformat()
        meta.bars_count = len(df)

        return df, meta

    def save_dataset(
        self,
        df: pd.DataFrame,
        symbol: str,
        timeframe: str = "H1",
        file_format: str = "parquet"
    ) -> DatasetMetadata:
        """
        Saves and validates a dataset into standard storage format.
        """
        sym = symbol.upper()
        tf = timeframe.upper()

        df_norm = self.validate_and_normalize(df, symbol=sym, timeframe=tf)

        sym_dir = self.storage_dir / sym
        sym_dir.mkdir(parents=True, exist_ok=True)

        if file_format.lower() == "parquet":
            target_path = sym_dir / f"{tf}.parquet"
            df_norm.to_parquet(target_path, index=False)
            fmt = "parquet"
        else:
            target_path = sym_dir / f"{tf}.csv"
            df_norm.to_csv(target_path, index=False)
            fmt = "csv"

        file_hash = self._compute_file_hash(target_path)

        meta = DatasetMetadata(
            symbol=sym,
            timeframe=tf,
            start_date=df_norm["time"].iloc[0].isoformat(),
            end_date=df_norm["time"].iloc[-1].isoformat(),
            bars_count=len(df_norm),
            file_path=str(target_path.resolve()),
            file_format=fmt,
            file_hash_sha256=file_hash,
            columns=list(df_norm.columns),
            created_at=datetime.now(timezone.utc).isoformat(),
        )

        # Save metadata sidecar JSON
        meta_json_path = sym_dir / f"{tf}_metadata.json"
        with open(meta_json_path, "w", encoding="utf-8") as f:
            json.dump(meta.to_dict(), f, indent=2)

        logger.info("[DataLoader] Saved dataset %s %s (%d bars, SHA-256: %s)", sym, tf, len(df_norm), file_hash[:12])
        return meta

    def list_available_datasets(self) -> List[Dict[str, Any]]:
        """Lists all historical datasets discovered in the storage directory."""
        datasets = []
        # Search for .parquet and .csv
        for p in self.storage_dir.rglob("*"):
            if p.is_file() and p.suffix.lower() in (".parquet", ".csv") and not p.name.startswith("."):
                try:
                    rel = p.relative_to(self.storage_dir)
                    parts = rel.parts
                    if len(parts) == 2:
                        sym = parts[0].upper()
                        tf = p.stem.upper()
                    else:
                        stem_parts = p.stem.split("_")
                        sym = stem_parts[0].upper()
                        tf = stem_parts[1].upper() if len(stem_parts) > 1 else "H1"

                    size_kb = round(p.stat().st_size / 1024, 1)
                    datasets.append({
                        "symbol": sym,
                        "timeframe": tf,
                        "format": p.suffix.lower().replace(".", ""),
                        "path": str(p),
                        "size_kb": size_kb,
                    })
                except Exception as e:
                    logger.debug("Error inspecting dataset %s: %s", p, e)

        return datasets


# Singleton instance
_data_loader_instance: Optional[DataLoader] = None

def get_data_loader(storage_dir: Optional[Union[str, Path]] = None) -> DataLoader:
    global _data_loader_instance
    if _data_loader_instance is None or storage_dir is not None:
        _data_loader_instance = DataLoader(storage_dir)
    return _data_loader_instance
