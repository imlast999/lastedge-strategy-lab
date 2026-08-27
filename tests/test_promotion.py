"""
Unit and Security Gate tests for StrategyPromotionService
tests/test_promotion.py
"""

import os
import json
import pytest
import tempfile
from pathlib import Path
from services.promotion import StrategyPromotionService


@pytest.fixture
def temp_lab():
    with tempfile.TemporaryDirectory() as tmpdir:
        p = Path(tmpdir)
        # Create a sample strategy source file
        src_file = p / "strategies" / "sample_strategy.py"
        src_file.parent.mkdir(parents=True, exist_ok=True)
        src_file.write_text("class SampleStrategy:\n    pass\n", encoding="utf-8")
        yield p, src_file


def test_promotion_case_a_valid_strategy_passes(temp_lab):
    lab_root, src_file = temp_lab
    svc = StrategyPromotionService(lab_root=lab_root)

    cand = svc.register_candidate(
        strategy_name="SampleStrategy",
        symbol="EURUSD",
        timeframe="H1",
        version="1.0.0",
        rules_config={"ema_fast": 20, "ema_slow": 50},
        validation_metrics={
            "baseline_backtest": {"signals": 120, "winrate": 55.0},
            "walk_forward": {"wes_score": 0.72, "passed": True},
            "monte_carlo": {"prob_ruin_pct": 1.2, "passed": True},
            "exit_research": {"stability_score": 28.5}
        },
        source_module_path=str(src_file),
        dataset_meta={"file_hash_sha256": "abcdef1234567890"}
    )

    engine_mock_dir = lab_root / "engine"
    engine_mock_dir.mkdir(parents=True, exist_ok=True)

    res = svc.promote_to_production(cand["candidate_id"], approver="Architect", target_engine_dir=engine_mock_dir)
    assert res["ok"] is True
    assert res["candidate"]["status"] == "APPROVED"
    assert res["export"]["verified"] is True
    assert (engine_mock_dir / "strategies" / "eurusd_v1_0_0.py").exists()
    assert (engine_mock_dir / "strategies" / "eurusd_v1_0_0.json").exists()


def test_promotion_case_b_failed_validation_metrics_blocked(temp_lab):
    lab_root, src_file = temp_lab
    svc = StrategyPromotionService(lab_root=lab_root)

    # Candidate with bad WES score (0.45 < 0.60) and high ruin (8.5% > 5.0%)
    cand = svc.register_candidate(
        strategy_name="FailingStrategy",
        symbol="EURUSD",
        timeframe="H1",
        version="1.0.0",
        rules_config={"ema": 10},
        validation_metrics={
            "baseline_backtest": {"signals": 50, "winrate": 40.0},
            "walk_forward": {"wes_score": 0.45, "passed": False},
            "monte_carlo": {"prob_ruin_pct": 8.5, "passed": False},
        },
        source_module_path=str(src_file)
    )

    res = svc.promote_to_production(cand["candidate_id"])
    assert res["ok"] is False
    assert "Promotion blocked by validation gates" in res["error"]
    assert any("Walk Forward" in r for r in res["reasons"])
    assert any("Monte Carlo" in r for r in res["reasons"])


def test_promotion_case_c_incomplete_pipeline_blocked(temp_lab):
    lab_root, src_file = temp_lab
    svc = StrategyPromotionService(lab_root=lab_root)

    # Missing Walk Forward and Monte Carlo
    cand = svc.register_candidate(
        strategy_name="IncompleteStrategy",
        symbol="XAUUSD",
        timeframe="H1",
        version="1.0.0",
        rules_config={"sl": 1.5},
        validation_metrics={
            "baseline_backtest": {"signals": 50, "winrate": 60.0},
        },
        source_module_path=str(src_file)
    )

    res = svc.promote_to_production(cand["candidate_id"])
    assert res["ok"] is False
    assert any("Walk Forward Analysis (WFA) was not executed" in r for r in res["reasons"])
    assert any("Monte Carlo stress testing was not executed" in r for r in res["reasons"])


def test_promotion_case_d_code_tampering_blocked(temp_lab):
    lab_root, src_file = temp_lab
    svc = StrategyPromotionService(lab_root=lab_root)

    cand = svc.register_candidate(
        strategy_name="SampleStrategy",
        symbol="EURUSD",
        timeframe="H1",
        version="1.0.0",
        rules_config={"ema_fast": 20},
        validation_metrics={
            "baseline_backtest": {"signals": 100, "winrate": 55.0},
            "walk_forward": {"wes_score": 0.70, "passed": True},
            "monte_carlo": {"prob_ruin_pct": 1.0, "passed": True},
        },
        source_module_path=str(src_file)
    )

    # Tamper with the source code file after registration
    src_file.write_text("class SampleStrategy:\n    # Tampered code!\n    pass\n", encoding="utf-8")

    res = svc.promote_to_production(cand["candidate_id"])
    assert res["ok"] is False
    assert any("Code SHA-256 mismatch" in r for r in res["reasons"])


def test_promotion_case_e_config_tampering_blocked(temp_lab):
    lab_root, src_file = temp_lab
    svc = StrategyPromotionService(lab_root=lab_root)

    cand = svc.register_candidate(
        strategy_name="SampleStrategy",
        symbol="EURUSD",
        timeframe="H1",
        version="1.0.0",
        rules_config={"ema_fast": 20},
        validation_metrics={
            "baseline_backtest": {"signals": 100, "winrate": 55.0},
            "walk_forward": {"wes_score": 0.70, "passed": True},
            "monte_carlo": {"prob_ruin_pct": 1.0, "passed": True},
        },
        source_module_path=str(src_file)
    )

    # Tamper with the manifest configuration directly
    manifest_path = lab_root / "data" / "candidates" / f"{cand['candidate_id']}.json"
    with open(manifest_path, "r") as f:
        data = json.load(f)
    data["rules_config"]["ema_fast"] = 999  # Changed parameter without updating hash
    with open(manifest_path, "w") as f:
        json.dump(data, f)

    res = svc.promote_to_production(cand["candidate_id"])
    assert res["ok"] is False
    assert any("Config hash mismatch" in r for r in res["reasons"])
