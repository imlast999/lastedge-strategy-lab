import pytest
import os
import tempfile
from pathlib import Path
from services.promotion import StrategyPromotionService


def test_strategy_candidate_lifecycle_and_promotion():
    with tempfile.TemporaryDirectory() as tmpdir:
        promo_svc = StrategyPromotionService(lab_root=Path(tmpdir))

        # 1. Register candidate
        cand = promo_svc.register_candidate(
            strategy_name="EURUSD_Asian_Breakout",
            symbol="EURUSD",
            timeframe="H1",
            version="1.2.0",
            rules_config={"sl_atr": 1.5, "tp_atr": 3.0, "asian_session_start": "00:00"},
            validation_metrics={"sharpe": 1.85, "winrate": 58.5, "max_dd": 4.2},
            source_module_path=os.path.abspath(__file__),
            notes="Validated on 20,000 bars WFA"
        )

        assert cand["status"] == "CANDIDATE"
        assert cand["version"] == "1.2.0"
        assert "config_hash" in cand

        # 2. List candidates
        all_cands = promo_svc.list_candidates()
        assert len(all_cands) == 1
        assert all_cands[0]["candidate_id"] == cand["candidate_id"]

        # 3. Promote candidate
        promoted = promo_svc.promote_to_production(
            candidate_id=cand["candidate_id"],
            approver="Quant_Lead"
        )
        assert promoted["ok"] is True
        assert promoted["candidate"]["status"] == "APPROVED"
        assert promoted["candidate"]["approved_by"] == "Quant_Lead"
