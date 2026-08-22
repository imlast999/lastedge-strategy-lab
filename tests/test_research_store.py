"""
Tests para ResearchStore (Research Database & Reproducibilidad) — tests/test_research_store.py
"""

import os
import tempfile
import unittest
from services.research_store import ResearchStore


class TestResearchStore(unittest.TestCase):

    def setUp(self):
        self.db_fd, self.db_path = tempfile.mkstemp(suffix='.db')
        self.temp_dir = tempfile.mkdtemp()
        self.store = ResearchStore(db_path=self.db_path, results_dir=self.temp_dir)

    def tearDown(self):
        os.close(self.db_fd)
        try:
            os.unlink(self.db_path)
        except Exception:
            pass

    def test_create_and_get_experiment(self):
        exp_data = {
            "experiment_id": "test_exp_001",
            "title": "Prueba Breakout XAUUSD",
            "hypothesis": "Probar SL=1.5x ATR y TP=4.5x ATR en XAUUSD H1",
            "symbol": "XAUUSD",
            "strategy": "xauusd_partial",
            "timeframe": "H1",
            "bars_count": 20000,
            "config": {"ema_period": 200, "atr_multiplier": 1.5},
            "tags": ["breakout", "xauusd"],
            "notes": "Resultado prometedor en 20k velas",
            "best_variant": "partial_close",
            "best_profit_factor": 1.92,
            "best_winrate": 56.4,
            "best_stability_score": 74.5,
            "decision_status": "CANDIDATE",
            "decision_notes": "Aprobado para forward testing"
        }

        exp_id = self.store.create_experiment(exp_data)
        self.assertEqual(exp_id, "test_exp_001")

        res = self.store.get_experiment("test_exp_001")
        self.assertIsNotNone(res)
        self.assertEqual(res['title'], "Prueba Breakout XAUUSD")
        self.assertEqual(res['symbol'], "XAUUSD")
        self.assertEqual(res['decision_status'], "CANDIDATE")
        self.assertEqual(res['best_profit_factor'], 1.92)
        self.assertEqual(res['config_json']['ema_period'], 200)

    def test_update_experiment(self):
        exp_data = {
            "experiment_id": "test_exp_002",
            "title": "Experimento Inicial",
            "symbol": "EURUSD",
            "strategy": "eurusd_partial"
        }
        self.store.create_experiment(exp_data)

        updated = self.store.update_experiment("test_exp_002", {
            "decision_status": "PROMOTED",
            "decision_notes": "Promocionado a producción tras pasar validación out-of-sample",
            "notes": "Notas finales actualizadas"
        })
        self.assertTrue(updated)

        res = self.store.get_experiment("test_exp_002")
        self.assertEqual(res['decision_status'], "PROMOTED")
        self.assertIn("producción", res['decision_notes'])
        self.assertEqual(res['notes'], "Notas finales actualizadas")

    def test_list_and_filter_experiments(self):
        self.store.create_experiment({
            "experiment_id": "exp_a", "title": "Alfa", "symbol": "EURUSD",
            "strategy": "eurusd_partial", "best_profit_factor": 1.8, "decision_status": "PROMOTED",
            "tags": ["gold", "v1"]
        })
        self.store.create_experiment({
            "experiment_id": "exp_b", "title": "Beta", "symbol": "BTCEUR",
            "strategy": "btceur_partial", "best_profit_factor": 1.1, "decision_status": "REJECTED",
            "tags": ["crypto"]
        })

        # Filtrar por símbolo
        exps, total = self.store.list_experiments(symbol="EURUSD")
        self.assertEqual(total, 1)
        self.assertEqual(exps[0]['experiment_id'], "exp_a")

        # Filtrar por decision_status
        exps_rej, total_rej = self.store.list_experiments(decision_status="REJECTED")
        self.assertEqual(total_rej, 1)
        self.assertEqual(exps_rej[0]['experiment_id'], "exp_b")

        # Filtrar por min_pf
        exps_pf, total_pf = self.store.list_experiments(min_pf=1.5)
        self.assertEqual(total_pf, 1)
        self.assertEqual(exps_pf[0]['experiment_id'], "exp_a")

    def test_reopen_payload(self):
        config_dict = {"sl_ratio": 1.5, "tp_ratio": 4.0, "timeframe": "H1"}
        self.store.create_experiment({
            "experiment_id": "exp_reopen",
            "title": "Prueba Reopen",
            "symbol": "XAUUSD",
            "strategy": "xauusd_partial",
            "config": config_dict
        })

        payload = self.store.get_reopen_payload("exp_reopen")
        self.assertIsNotNone(payload)
        self.assertEqual(payload['experiment_id'], "exp_reopen")
        self.assertEqual(payload['config']['sl_ratio'], 1.5)
        self.assertIn('reopened_at', payload)


if __name__ == '__main__':
    unittest.main()
