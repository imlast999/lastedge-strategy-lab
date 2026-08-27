"""
End-to-End Research -> Validation -> Promotion -> Trading Engine Integration Test
tests/test_end_to_end_research.py
"""

import os
import json
import pytest
import tempfile
import pandas as pd
import numpy as np
from datetime import datetime, timezone, timedelta
from pathlib import Path

from services.data_loader import DataLoader
from services.promotion import StrategyPromotionService
from core.replay_engine import ReplayEngine
from core.walkforward import WalkForwardTester
from core.montecarlo import MonteCarlo
from strategies.base import BaseStrategy, StrategyMetadata


class DummyTrendStrategy(BaseStrategy):
    """Dummy strategy implementing BaseStrategy contract for E2E integration."""

    def __init__(self):
        super().__init__(name="test_trend_pullback")

    @property
    def metadata(self) -> StrategyMetadata:
        return StrategyMetadata(
            required_history=60,
            symbol="EURUSD",
            timeframe="H1",
            strategy_name="test_trend_pullback",
            version="1.0.0"
        )

    def _get_default_config(self):
        return {"ema_fast": 5, "ema_slow": 15, "sl_pips": 15.0, "tp_pips": 30.0}

    def _add_specific_indicators(self, df: pd.DataFrame, config):
        df = df.copy()
        df["ema_fast"] = df["close"].ewm(span=config.get("ema_fast", 5)).mean()
        df["ema_slow"] = df["close"].ewm(span=config.get("ema_slow", 15)).mean()
        return df

    def detect_setup(self, df: pd.DataFrame, config=None):
        if len(df) < 60:
            return None
        cfg = {**self.default_config, **(config or {})}
        df_ind = self.add_indicators(df, cfg)
        last = df_ind.iloc[-1]
        prev = df_ind.iloc[-2]

        if prev["ema_fast"] <= prev["ema_slow"] and last["ema_fast"] > last["ema_slow"]:
            entry = float(last["close"])
            return {
                "type": "BUY",
                "entry": entry,
                "sl": entry - 0.0015,
                "tp": entry + 0.0030,
                "timeframe": "H1"
            }
        elif prev["ema_fast"] >= prev["ema_slow"] and last["ema_fast"] < last["ema_slow"]:
            entry = float(last["close"])
            return {
                "type": "SELL",
                "entry": entry,
                "sl": entry + 0.0015,
                "tp": entry - 0.0030,
                "timeframe": "H1"
            }
        return None


def test_end_to_end_research_to_promotion_lifecycle():
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        lab_dir = root / "strategy_lab"
        engine_dir = root / "trading_engine"
        lab_dir.mkdir(parents=True, exist_ok=True)
        engine_dir.mkdir(parents=True, exist_ok=True)

        # 1. Create and save realistic synthetic dataset via DataLoader
        loader = DataLoader(storage_dir=lab_dir / "data" / "historical")
        base_time = datetime(2026, 1, 1, 0, 0, tzinfo=timezone.utc)
        dates = [base_time + timedelta(hours=i) for i in range(1200)]
        np.random.seed(42)
        # Create clear trending waves so strategy generates winning setups
        trend = np.sin(np.linspace(0, 15, 1200)) * 0.0100 + np.linspace(0, 0.0200, 1200)
        closes = 1.0800 + trend + np.random.randn(1200) * 0.0003
        opens = closes - np.random.randn(1200) * 0.0002
        highs = np.maximum(opens, closes) + 0.0005
        lows = np.minimum(opens, closes) - 0.0005
        volumes = np.random.randint(100, 500, size=1200)

        df_synthetic = pd.DataFrame({
            "time": dates,
            "open": opens,
            "high": highs,
            "low": lows,
            "close": closes,
            "volume": volumes,
        })

        data_meta = loader.save_dataset(df_synthetic, symbol="EURUSD", timeframe="H1", file_format="parquet")
        assert Path(data_meta.file_path).exists()
        assert len(data_meta.file_hash_sha256) == 64

        # 2. Run Replay Backtest offline
        strat = DummyTrendStrategy()
        replay = ReplayEngine(lookback_window=strat.metadata.required_history)
        stats = replay.run_replay(
            symbol="EURUSD",
            bars=len(df_synthetic) - strat.metadata.required_history,
            timeframe="H1",
            df_override=df_synthetic
        )
        assert stats.bars_analyzed > 0

        # 3. Run Monte Carlo Simulation on simulated replay signals
        from core.replay_engine import ReplaySignal
        sim_signals = []
        for i in range(50):
            # 60% win rate trades
            is_win = (i % 5 != 0)
            pips = 20.0 if is_win else -10.0
            res_str = "WIN" if is_win else "LOSS"
            sim_signals.append(ReplaySignal(
                timestamp=base_time + timedelta(hours=i*20),
                symbol="EURUSD",
                signal_type="BUY",
                entry=1.0800,
                sl=1.0790,
                tp=1.0820,
                confidence="HIGH",
                score=85.0,
                bar_index=i*20,
                result=res_str,
                profit_pips=pips
            ))

        mc = MonteCarlo(n_simulations=1000, seed=42)
        mc_report = mc.run(sim_signals, symbol="EURUSD")
        assert mc_report.prob_ruin <= 0.05

        # 4. Save Strategy File
        strat_file = lab_dir / "strategies" / "test_trend_strategy.py"
        strat_file.parent.mkdir(parents=True, exist_ok=True)
        strat_file.write_text("""
from strategies.base import BaseStrategy, StrategyMetadata
import pandas as pd

class TestTrendStrategy(BaseStrategy):
    def __init__(self):
        super().__init__(name='test_trend_pullback')
    @property
    def metadata(self):
        return StrategyMetadata(60, 'EURUSD', 'H1', 'test_trend_pullback', '1.0.0')
    def _get_default_config(self):
        return {'ema_fast': 5, 'ema_slow': 15}
    def _add_specific_indicators(self, df, cfg):
        return df
    def detect_setup(self, df, cfg=None):
        return None
""", encoding="utf-8")

        # 5. Register Candidate with Full Validation Metrics & Hashes
        promo_svc = StrategyPromotionService(lab_root=lab_dir)
        cand = promo_svc.register_candidate(
            strategy_name=strat.metadata.strategy_name,
            symbol=strat.metadata.symbol,
            timeframe=strat.metadata.timeframe,
            version=strat.metadata.version,
            rules_config=strat._get_default_config(),
            validation_metrics={
                "baseline_backtest": {"signals": len(sim_signals), "winrate": 60.0},
                "walk_forward": {"wes_score": 0.85, "passed": True},
                "monte_carlo": {"prob_ruin_pct": mc_report.prob_ruin * 100, "passed": True},
                "exit_research": {"stability_score": 35.0}
            },
            source_module_path=str(strat_file),
            dataset_meta=data_meta.to_dict(),
            notes="End-to-end integration test candidate"
        )

        assert cand["status"] == "CANDIDATE"
        assert len(cand["code_sha256"]) == 64
        assert len(cand["config_hash"]) == 16
        assert cand["dataset_sha256"] == data_meta.file_hash_sha256

        # 6. Promote Candidate to Engine
        res = promo_svc.promote_to_production(
            candidate_id=cand["candidate_id"],
            approver="Architect",
            target_engine_dir=engine_dir
        )

        assert res["ok"] is True
        assert res["candidate"]["status"] == "APPROVED"
        assert res["export"]["verified"] is True

        # 7. Verify Engine destination package
        dest_py = engine_dir / "strategies" / "eurusd_v1_0_0.py"
        dest_json = engine_dir / "strategies" / "eurusd_v1_0_0.json"
        assert dest_py.exists()
        assert dest_json.exists()

        manifest = json.loads(dest_json.read_text(encoding="utf-8"))
        assert manifest["strategy_name"] == "test_trend_pullback"
        assert manifest["code_sha256"] == cand["code_sha256"]
        assert manifest["dataset_sha256"] == data_meta.file_hash_sha256
