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
    assert "scoring_analysis" in res
    assert "buckets" in res["scoring_analysis"]


def test_scoring_calibration_and_buckets():
    svc = get_backtest_service()
    from core.replay_engine import ReplaySignal
    from datetime import datetime, timezone

    now = datetime.now(timezone.utc)
    mock_trades = [
        ReplaySignal(timestamp=now, symbol="EURUSD", signal_type="BUY", entry=1.1, sl=1.09, tp=1.12, confidence="VERY_HIGH", score=0.92, bar_index=1, result="WIN", profit_pips=20.0),
        ReplaySignal(timestamp=now, symbol="EURUSD", signal_type="BUY", entry=1.1, sl=1.09, tp=1.12, confidence="VERY_HIGH", score=0.88, bar_index=2, result="WIN", profit_pips=18.0),
        ReplaySignal(timestamp=now, symbol="EURUSD", signal_type="BUY", entry=1.1, sl=1.09, tp=1.12, confidence="HIGH", score=0.74, bar_index=3, result="WIN", profit_pips=10.0),
        ReplaySignal(timestamp=now, symbol="EURUSD", signal_type="SELL", entry=1.1, sl=1.11, tp=1.08, confidence="HIGH", score=0.71, bar_index=4, result="LOSS", profit_pips=-10.0),
        ReplaySignal(timestamp=now, symbol="EURUSD", signal_type="SELL", entry=1.1, sl=1.11, tp=1.08, confidence="MEDIUM", score=0.64, bar_index=5, result="LOSS", profit_pips=-10.0),
        ReplaySignal(timestamp=now, symbol="EURUSD", signal_type="SELL", entry=1.1, sl=1.11, tp=1.08, confidence="MEDIUM", score=0.62, bar_index=6, result="LOSS", profit_pips=-10.0),
    ]

    analysis = svc._compute_scoring_analysis(mock_trades)
    assert analysis["has_data"] is True
    assert analysis["total_trades"] == 6
    assert analysis["avg_score_winners"] > analysis["avg_score_losers"]
    assert analysis["score_edge_delta"] > 0
    assert analysis["is_calibrated"] is True
    assert len(analysis["buckets"]) == 5
    
    # Check Elite Bucket
    elite = [b for b in analysis["buckets"] if b["tier"] == "ELITE"][0]
    assert elite["trades_count"] == 1
    assert elite["wins"] == 1
    assert elite["win_rate_pct"] == 100.0

    # Check Medium Bucket
    medium = [b for b in analysis["buckets"] if b["tier"] == "MEDIUM"][0]
    assert medium["trades_count"] == 2
    assert medium["losses"] == 2
    assert medium["win_rate_pct"] == 0.0
