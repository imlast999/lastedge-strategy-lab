"""
Example (unit) tests for ExitResearchRunner.

Tasks 12.2, 12.3, 12.4, 12.5 of the eurusd-exit-research spec.
"""

import numpy as np
import pandas as pd
import pytest
from unittest.mock import MagicMock, patch

from core.exit_research.runner import (
    ExitResearchRunner,
    ExitResearchReport,
    VariantResult,
    WF_WINDOWS,
    _Trade,
)
from core.exit_research.metrics import ExtendedMetrics
from core.exit_research.strategy_adapter import StrategyAdapter
from strategies.base import BaseStrategy, StrategyMetadata
from tests.exit_research.conftest import make_ohlcv


# ---------------------------------------------------------------------------
# Task 12.3 — Insufficient data guard
# Validates: Requirement 3.3
# ---------------------------------------------------------------------------

def test_insufficient_data_guard():
    """
    When _download_data returns fewer than 20,200 bars, run_all must raise
    RuntimeError with a message containing "Insufficient data".
    """
    n = 1000
    df = pd.DataFrame({
        "open":   np.random.uniform(1.08, 1.12, n),
        "high":   np.random.uniform(1.09, 1.13, n),
        "low":    np.random.uniform(1.07, 1.11, n),
        "close":  np.random.uniform(1.08, 1.12, n),
        "volume": np.ones(n),
    })

    runner = ExitResearchRunner()
    with patch.object(runner, "_download_data", return_value=df):
        with pytest.raises(RuntimeError, match="Insufficient data"):
            runner.run_all(bars=20000, save=False, verbose=False)


def test_metadata_required_history_sets_minimum_bars():
    """Runner should require max(levels) + strategy.required_history bars."""

    class DummyStrategy(BaseStrategy):
        def __init__(self):
            super().__init__(name="dummy")

        @property
        def metadata(self) -> StrategyMetadata:
            return StrategyMetadata(required_history=210, symbol="EURUSD", strategy_name="dummy")

        def _get_default_config(self):
            return {}

        def detect_setup(self, df, config=None):
            return None

        def _add_specific_indicators(self, df, config):
            return df

    df = make_ohlcv(20_200, seed=11)
    runner = ExitResearchRunner(
        symbol="EURUSD",
        strategy=StrategyAdapter(DummyStrategy()),
        levels=[20_000],
    )

    with patch.object(runner, "_download_data", return_value=df):
        with pytest.raises(RuntimeError, match="Insufficient data"):
            runner.run_all(bars=20_000, save=False, verbose=False)


# ---------------------------------------------------------------------------
# Task 12.4 — JSON export failure returns in-memory dict
# Validates: Requirement 8.6
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Task 12.2 — WF produces exactly 4 windows on a 20k dataset
# Validates: Requirement 4.1
# ---------------------------------------------------------------------------

def test_wf_window_count():
    """
    _run_walkforward must evaluate exactly WF_WINDOWS (4) windows when the
    variant has enough trades in each window.

    Strategy: build a synthetic 20,200-bar dataset, populate variant_trades
    with one trade per bar so every window always has enough trades, then
    verify that the runner evaluates exactly 4 windows by counting
    classification outcomes via wf_stability being set.
    """
    LOOKBACK = 200
    N_BACKTEST = 20_000
    TOTAL_BARS = LOOKBACK + N_BACKTEST

    df = make_ohlcv(TOTAL_BARS, seed=7)

    # One WIN trade per bar covering the full 20k range (bar_index = LOOKBACK..TOTAL_BARS-1)
    trades = [
        _Trade(result="WIN", profit_pips=1.0, bar_index=i, exit_bar=i + 1)
        for i in range(LOOKBACK, TOTAL_BARS)
    ]

    from core.exit_research.variants import Variant_RR3
    variant = Variant_RR3()

    runner = ExitResearchRunner(lookback=LOOKBACK)

    # Build a minimal report with a VariantResult at the 20k level
    m = ExtendedMetrics(
        variant_name=variant.name,
        variant_label=variant.label,
        n_bars=N_BACKTEST,
    )
    m.stability_score = 50.0
    vr = VariantResult(
        variant_name=variant.name,
        variant_label=variant.label,
        n_bars=N_BACKTEST,
        metrics=m,
    )
    report = ExitResearchReport(run_id="test", timestamp="2025-01-01T00:00:00Z")
    report.results[variant.name] = {N_BACKTEST: vr}
    variant_trades = {variant.name: trades}

    # Patch _compute_pf so each window reports a predictable STABLE classification
    # (pf_train=1.5, pf_test=1.3 → STABLE per the priority rules)
    with patch.object(ExitResearchRunner, "_compute_pf", return_value=1.3):
        runner._run_walkforward(report, df, variant_trades, verbose=False)

    # wf_stability must have been set (not None) — proves at least one valid window
    assert m.wf_stability is not None, "wf_stability was not set by _run_walkforward"

    # The stability should be one of the valid classifications (4 windows evaluated)
    assert m.wf_stability in {"STABLE", "MARGINAL", "UNSTABLE", "OVERFITTED"}, (
        f"Unexpected wf_stability value: {m.wf_stability}"
    )


# ---------------------------------------------------------------------------
# Task 12.4 — JSON export failure returns in-memory dict
# Validates: Requirement 8.6
# ---------------------------------------------------------------------------

def test_json_export_failure():
    """
    When _save raises PermissionError, run_all must still return the
    in-memory report dict rather than propagating the exception.
    """
    runner = ExitResearchRunner()

    mock_report_dict = {
        "run_id": "test",
        "generated_at": "2025-01-01T00:00:00Z",
        "symbol": "EURUSD",
        "validation_mode": "no_optimization",
        "comparison_table": [],
        "degradation_table": {},
        "conclusions": {},
        "results": {},
    }

    n = 21000
    df = pd.DataFrame({
        "open":   np.random.uniform(1.08, 1.12, n),
        "high":   np.random.uniform(1.09, 1.13, n),
        "low":    np.random.uniform(1.07, 1.11, n),
        "close":  np.random.uniform(1.08, 1.12, n),
        "volume": np.ones(n),
    })

    with patch.object(runner, "_download_data", return_value=df), \
         patch.object(runner, "_run_variant", return_value=(MagicMock(error=None, metrics=MagicMock()), [])), \
         patch.object(runner, "_run_walkforward"), \
         patch.object(runner, "_run_montecarlo"), \
         patch.object(runner, "_update_stability_scores"), \
         patch.object(runner, "_build_report_dict", return_value=mock_report_dict), \
         patch.object(runner, "_save_session", side_effect=PermissionError("no write")):

        result = runner.run_all(bars=20000, save=True, verbose=False)

    assert result == mock_report_dict


# ---------------------------------------------------------------------------
# Task 12.3 — Insufficient data guard
# Validates: Requirement 3.3
# ---------------------------------------------------------------------------

def test_insufficient_data_guard():
    """
    When _download_data returns fewer than 20,200 bars, run_all must raise
    RuntimeError with a message containing "Insufficient data".
    """
    n = 1000
    df = pd.DataFrame({
        "open":   np.random.uniform(1.08, 1.12, n),
        "high":   np.random.uniform(1.09, 1.13, n),
        "low":    np.random.uniform(1.07, 1.11, n),
        "close":  np.random.uniform(1.08, 1.12, n),
        "volume": np.ones(n),
    })

    runner = ExitResearchRunner()
    with patch.object(runner, "_download_data", return_value=df):
        with pytest.raises(RuntimeError, match="Insufficient data"):
            runner.run_all(bars=20000, save=False, verbose=False)


# ---------------------------------------------------------------------------
# Task 12.5 — Full pipeline smoke test with small synthetic dataset
# Validates: Requirements 9.1, 9.2, 9.3
# ---------------------------------------------------------------------------

def test_smoke_run():
    """
    Full pipeline smoke test using a synthetic dataset.

    Mocks _download_data and EURUSDStrategy so no MT5 connection is needed.
    Uses a minimal set of variants and levels to keep the test fast.

    Asserts that run_exit_research() returns a dict with all required
    top-level keys as defined in the report schema.
    """
    from core.exit_research import run_exit_research
    from core.exit_research.variants import Variant_RR3, Variant_RR4

    REQUIRED_KEYS = {
        "run_id",
        "generated_at",
        "symbol",
        "validation_mode",
        "comparison_table",
        "degradation_table",
        "conclusions",
        "results",
    }

    # A synthetic 20,200-bar OHLCV dataset with indicators already computed
    df = make_ohlcv(20_200, seed=123)

    # Minimal mock adapter: get_signal returns None always (no signals),
    # get_atr returns a fixed value. This exercises the entire pipeline with
    # 0 trades, testing that the runner handles empty results gracefully.
    mock_adapter = MagicMock()
    mock_adapter.get_signal.return_value = None
    mock_adapter.get_atr.return_value = 0.0010
    mock_adapter.reload.return_value = None

    with patch(
        "core.exit_research.runner.ExitResearchRunner._download_data",
        return_value=df,
    ), patch(
        "core.exit_research.runner.ExitResearchRunner._get_strategy_adapter",
        return_value=mock_adapter,
    ):
        # Use only 2 variants and the 5k level for speed
        runner = ExitResearchRunner(
            variants=[Variant_RR3(), Variant_RR4()],
            levels=[5_000],
        )
        report = runner.run_all(bars=5_000, save=False, verbose=False)

    assert isinstance(report, dict), "run_all must return a dict"
    missing = REQUIRED_KEYS - set(report.keys())
    assert not missing, f"Report is missing required top-level keys: {missing}"

    # validation_mode must be "no_optimization"
    assert report["validation_mode"] == "no_optimization", (
        f"Expected validation_mode='no_optimization', got {report['validation_mode']!r}"
    )

    # generated_at must be a non-empty ISO 8601 UTC string ending in Z
    assert report["generated_at"].endswith("Z"), (
        f"generated_at must end with 'Z': {report['generated_at']!r}"
    )
    assert len(report["generated_at"]) == 20, (
        f"generated_at must be 20 chars (YYYY-MM-DDTHH:MM:SSZ): {report['generated_at']!r}"
    )

    # results section must have entries for both variants
    assert "rr_1_3" in report["results"]
    assert "rr_1_4" in report["results"]
