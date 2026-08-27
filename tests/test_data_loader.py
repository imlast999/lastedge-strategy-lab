"""
Unit tests for Historical DataLoader & Storage Service
tests/test_data_loader.py
"""

import os
import shutil
import tempfile
import pytest
import pandas as pd
import numpy as np
from datetime import datetime, timezone, timedelta
from pathlib import Path

from services.data_loader import DataLoader, DatasetValidationError, DatasetMetadata


@pytest.fixture
def temp_storage():
    d = tempfile.mkdtemp(prefix="lastedge_test_data_")
    yield Path(d)
    shutil.rmtree(d, ignore_errors=True)


@pytest.fixture
def sample_ohlcv_df():
    base_time = datetime(2026, 1, 1, 0, 0, tzinfo=timezone.utc)
    dates = [base_time + timedelta(hours=i) for i in range(100)]
    np.random.seed(42)
    closes = 1.0800 + np.cumsum(np.random.randn(100) * 0.0010)
    opens = closes + np.random.randn(100) * 0.0005
    highs = np.maximum(opens, closes) + 0.0005
    lows = np.minimum(opens, closes) - 0.0005
    volumes = np.random.randint(100, 1000, size=100)

    return pd.DataFrame({
        "time": dates,
        "open": opens,
        "high": highs,
        "low": lows,
        "close": closes,
        "volume": volumes,
    })


def test_dataloader_save_and_load_parquet(temp_storage, sample_ohlcv_df):
    loader = DataLoader(storage_dir=temp_storage)

    # Save as parquet
    meta = loader.save_dataset(sample_ohlcv_df, symbol="EURUSD", timeframe="H1", file_format="parquet")
    assert meta.symbol == "EURUSD"
    assert meta.timeframe == "H1"
    assert meta.bars_count == 100
    assert meta.file_format == "parquet"
    assert len(meta.file_hash_sha256) == 64
    assert Path(meta.file_path).exists()

    # Load back
    df_loaded, meta_loaded = loader.load(symbol="EURUSD", timeframe="H1")
    assert len(df_loaded) == 100
    assert list(df_loaded.columns[:6]) == ["time", "open", "high", "low", "close", "volume"]
    assert meta_loaded.bars_count == 100


def test_dataloader_save_and_load_csv(temp_storage, sample_ohlcv_df):
    loader = DataLoader(storage_dir=temp_storage)

    # Save as CSV
    meta = loader.save_dataset(sample_ohlcv_df, symbol="XAUUSD", timeframe="M15", file_format="csv")
    assert meta.symbol == "XAUUSD"
    assert meta.file_format == "csv"

    # Load back
    df_loaded, meta_loaded = loader.load(symbol="XAUUSD", timeframe="M15")
    assert len(df_loaded) == 100
    assert df_loaded["close"].iloc[0] == pytest.approx(sample_ohlcv_df["close"].iloc[0])


def test_dataloader_deduplication_and_sorting(temp_storage):
    loader = DataLoader(storage_dir=temp_storage)

    # Create un-sorted df with duplicate timestamp
    t1 = datetime(2026, 1, 1, 10, 0, tzinfo=timezone.utc)
    t2 = datetime(2026, 1, 1, 9, 0, tzinfo=timezone.utc)
    t3 = datetime(2026, 1, 1, 11, 0, tzinfo=timezone.utc)

    df_messy = pd.DataFrame({
        "timestamp": [t1, t2, t1, t3],  # t1 repeated, unsorted
        "open": [1.0, 1.0, 1.05, 1.0],
        "high": [1.2, 1.2, 1.25, 1.2],
        "low": [0.8, 0.8, 0.85, 0.8],
        "close": [1.1, 1.1, 1.15, 1.1],
        "vol": [10, 10, 20, 10],
    })

    df_clean = loader.validate_and_normalize(df_messy, symbol="BTCEUR", timeframe="H1")
    assert len(df_clean) == 3
    # Check sorted
    assert df_clean["time"].iloc[0] == t2
    assert df_clean["time"].iloc[1] == t1
    assert df_clean["time"].iloc[2] == t3
    # Check duplicate kept last observation (open=1.05)
    assert df_clean["open"].iloc[1] == 1.05


def test_dataloader_validation_errors(temp_storage):
    loader = DataLoader(storage_dir=temp_storage)

    # Empty df
    with pytest.raises(DatasetValidationError, match="empty"):
        loader.validate_and_normalize(pd.DataFrame())

    # Missing columns
    with pytest.raises(DatasetValidationError, match="Missing required price columns"):
        loader.validate_and_normalize(pd.DataFrame({"time": [datetime.now()], "open": [1.0]}))

    # Invalid high < low
    with pytest.raises(DatasetValidationError, match="High < Low"):
        loader.validate_and_normalize(pd.DataFrame({
            "time": [datetime.now(timezone.utc)],
            "open": [10.0],
            "high": [8.0],  # High < Low
            "low": [9.0],
            "close": [8.5],
            "volume": [100]
        }))


def test_dataloader_list_datasets(temp_storage, sample_ohlcv_df):
    loader = DataLoader(storage_dir=temp_storage)

    loader.save_dataset(sample_ohlcv_df, symbol="EURUSD", timeframe="H1", file_format="parquet")
    loader.save_dataset(sample_ohlcv_df, symbol="BTCEUR", timeframe="D1", file_format="csv")

    datasets = loader.list_available_datasets()
    assert len(datasets) == 2
    symbols = {d["symbol"] for d in datasets}
    assert "EURUSD" in symbols
    assert "BTCEUR" in symbols
