"""
Unit tests for run_pipeline.py unified research CLI
tests/test_run_pipeline.py
"""

import os
import sys
import json
import pytest
import subprocess
import tempfile
import pandas as pd
import numpy as np
from datetime import datetime, timezone, timedelta
from pathlib import Path

from services.data_loader import DataLoader


@pytest.fixture
def prepared_lab_env():
    """Sets up a temporary dataset and returns its path."""
    temp_dir = tempfile.mkdtemp(prefix="lab_pipeline_test_")
    loader = DataLoader(storage_dir=temp_dir)

    base_time = datetime(2026, 1, 1, 0, 0, tzinfo=timezone.utc)
    dates = [base_time + timedelta(hours=i) for i in range(500)]
    np.random.seed(42)
    closes = 1.0800 + np.cumsum(np.random.randn(500) * 0.0005)
    opens = closes + np.random.randn(500) * 0.0002
    highs = np.maximum(opens, closes) + 0.0003
    lows = np.minimum(opens, closes) - 0.0003
    volumes = np.random.randint(100, 500, size=500)

    df = pd.DataFrame({
        "time": dates,
        "open": opens,
        "high": highs,
        "low": lows,
        "close": closes,
        "volume": volumes,
    })

    meta = loader.save_dataset(df, symbol="EURUSD", timeframe="H1", file_format="parquet")
    yield meta.file_path, temp_dir


def test_run_pipeline_cli_execution(prepared_lab_env):
    data_file, temp_dir = prepared_lab_env
    lab_root = Path(__file__).parent.parent

    cmd = [
        sys.executable,
        str(lab_root / "run_pipeline.py"),
        "--symbol", "EURUSD",
        "--strategy", "eurusd_simple",
        "--data-file", str(data_file),
        "--skip-wfa",
        "--skip-exit-research",
        "--json"
    ]

    env = os.environ.copy()
    env["HISTORICAL_DATA_DIR"] = str(temp_dir)

    result = subprocess.run(cmd, cwd=str(lab_root), capture_output=True, text=True, env=env)
    assert result.returncode == 0, f"run_pipeline failed with: {result.stderr}"
    assert "RESEARCH PIPELINE COMPLETED SUCCESSFULLY FOR EURUSD" in result.stdout
    assert "JSON PIPELINE REPORT" in result.stdout
