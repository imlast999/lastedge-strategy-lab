"""
Shared fixtures for exit_research tests.

Provides synthetic OHLCV DataFrames that do not require a live MT5 connection.
"""
import numpy as np
import pandas as pd
import pytest


def make_ohlcv(n_bars: int, seed: int = 42) -> pd.DataFrame:
    """
    Build a deterministic synthetic OHLCV DataFrame with ATR and EMA columns.

    The price series is a simple random-walk around 1.10000 so that all
    derived indicator columns (ema20, ema50, ema200, atr) are finite and
    positive.  No MT5 connection is required.

    Parameters
    ----------
    n_bars : int
        Number of bars to generate.
    seed : int
        RNG seed for reproducibility.

    Returns
    -------
    pd.DataFrame
        Columns: open, high, low, close, volume, atr, ema20, ema50, ema200, rsi
    """
    rng = np.random.default_rng(seed)
    pip = 0.0001

    # Simple random walk for close prices
    returns = rng.normal(0, 5 * pip, n_bars)
    close = 1.10000 + np.cumsum(returns)
    close = np.clip(close, 1.0500, 1.2500)

    spread = rng.uniform(2 * pip, 6 * pip, n_bars)
    open_  = close - rng.uniform(-3 * pip, 3 * pip, n_bars)
    high   = np.maximum(close, open_) + spread
    low    = np.minimum(close, open_) - spread

    volume = rng.integers(100, 5000, n_bars).astype(float)

    df = pd.DataFrame({
        "open":   open_,
        "high":   high,
        "low":    low,
        "close":  close,
        "volume": volume,
    })

    # ATR (14-period simple approximation using true range)
    tr = pd.Series(high - low)
    df["atr"] = tr.rolling(14, min_periods=1).mean()

    # EMAs
    df["ema20"]  = df["close"].ewm(span=20,  adjust=False).mean()
    df["ema50"]  = df["close"].ewm(span=50,  adjust=False).mean()
    df["ema200"] = df["close"].ewm(span=200, adjust=False).mean()

    # RSI (14-period)
    delta = df["close"].diff()
    gain  = delta.clip(lower=0).rolling(14, min_periods=1).mean()
    loss  = (-delta.clip(upper=0)).rolling(14, min_periods=1).mean()
    rs    = gain / (loss + 1e-12)
    df["rsi"] = 100 - 100 / (1 + rs)

    return df


@pytest.fixture
def synthetic_ohlcv_200():
    """200-bar OHLCV DataFrame (lookback window)."""
    return make_ohlcv(200)


@pytest.fixture
def synthetic_ohlcv_20200():
    """20,200-bar OHLCV DataFrame (200 lookback + 20,000 backtest bars)."""
    return make_ohlcv(20_200)
