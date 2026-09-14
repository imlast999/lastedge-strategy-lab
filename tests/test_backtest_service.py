"""
LastEdge Strategy Lab — Tests for BacktestService and Verdict Engine
tests/test_backtest_service.py
"""

import pytest
from services.backtest_service import BacktestService, get_backtest_service


def test_backtest_service_singleton():
    svc1 = get_backtest_service()
    svc2 = get_backtest_service()
    assert svc1 is svc2
    assert isinstance(svc1, BacktestService)


def test_verdict_evaluation_tiers():
    svc = get_backtest_service()

    # Tier 1: Highly Reliable
    v1 = svc._evaluate_verdict(
        profit_factor=1.65,
        sharpe_ratio=1.85,
        max_dd_pct=11.2,
        win_rate=58.0,
        expectancy_pips=8.5,
        total_trades=80,
        ruin_prob_pct=0.4,
        consecutive_losses=3,
    )
    assert v1["tier"] == "TIER_1_RELIABLE"
    assert v1["status_tag"] == "PROMOTED"
    assert "PRODUCCIÓN" in v1["title"]
    assert len(v1["recommendations"]) >= 3

    # Tier 2: Needs Optimization
    v2 = svc._evaluate_verdict(
        profit_factor=1.18,
        sharpe_ratio=1.05,
        max_dd_pct=18.5,
        win_rate=47.0,
        expectancy_pips=2.1,
        total_trades=65,
        ruin_prob_pct=3.2,
        consecutive_losses=5,
    )
    assert v2["tier"] == "TIER_2_OPTIMIZE"
    assert v2["status_tag"] == "CANDIDATE"
    assert "OPTIMIZACIÓN" in v2["title"]

    # Tier 3: Rejected / Critical Risk
    v3 = svc._evaluate_verdict(
        profit_factor=0.82,
        sharpe_ratio=-0.45,
        max_dd_pct=34.0,
        win_rate=32.0,
        expectancy_pips=-5.6,
        total_trades=90,
        ruin_prob_pct=18.5,
        consecutive_losses=11,
    )
    assert v3["tier"] == "TIER_3_REJECTED"
    assert v3["status_tag"] == "REJECTED"
    assert "DESCARTADA" in v3["title"]
    assert "reasons" in v3["summary"].lower() or "destructivo" in v3["summary"].lower() or "drawdown" in v3["summary"].lower()


def test_run_backtest_returns_valid_structure():
    svc = get_backtest_service()
    res = svc.run_backtest(symbol="EURUSD", timeframe="H1", bars=500)
    assert res["ok"] is True
    assert "metrics" in res
    assert "verdict" in res
    assert "total_trades" in res["metrics"]
    assert "profit_factor" in res["metrics"]
    assert "recommendations" in res["verdict"]
