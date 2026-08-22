"""
Tests completos para P5.3 — Long Forward Validation & Longevity Engine
========================================================================
Verifica:
  1. Persistencia de tabla long_forward_sessions e interrupción automática al reiniciar.
  2. Integración de métricas de trading reales (señales, trades, rechazadas, DD).
  3. Rastreo automático de downtime MT5 (disconnect/reconnect).
  4. Cálculo del "Forward Validation Score" (0.0 - 100.0).
  5. Explorador histórico de sesiones (list_sessions, get_session).
"""

from __future__ import annotations

import os
import unittest
import tempfile
from datetime import datetime, timezone
from services.database import get_database_manager
from services.long_forward_validation import (
    LongForwardValidationService,
    get_long_forward_validation_service,
)


class TestP53LongForwardValidation(unittest.TestCase):

    def setUp(self):
        self.tmp_db = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.tmp_db.close()
        self.db_path = self.tmp_db.name
        self.db_manager = get_database_manager(self.db_path)

        # Crear esquema básico con tablas para probar integración con trading
        with self.db_manager.get_connection() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS enhanced_signals (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    symbol TEXT, strategy TEXT
                );
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS trade_journal (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    symbol TEXT, execution_status TEXT
                );
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS balance_snapshots (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    balance REAL, equity REAL, floating_pnl REAL
                );
            """)
            # Datos sintéticos
            conn.execute("INSERT INTO enhanced_signals (symbol, strategy) VALUES ('EURUSD', 'trend');")
            conn.execute("INSERT INTO trade_journal (symbol, execution_status) VALUES ('EURUSD', 'SUCCESS');")
            conn.execute("INSERT INTO trade_journal (symbol, execution_status) VALUES ('XAUUSD', 'REJECTED');")
            conn.execute("INSERT INTO balance_snapshots (balance, equity, floating_pnl) VALUES (10000.0, 9800.0, -200.0);")

        self.svc = LongForwardValidationService(self.db_path)

    def tearDown(self):
        try:
            os.remove(self.db_path)
        except Exception:
            pass

    def test_session_persistence_and_auto_interruption(self):
        # 1. Iniciar sesión en servicio A
        res = self.svc.start_session("24h")
        session_id = res["session_id"]
        self.assertTrue(self.svc.session_active)

        # 2. Instanciar servicio B apuntando a la misma BD (Simular reinicio de aplicación)
        svc_b = LongForwardValidationService(self.db_path)

        # 3. La sesión abandonada debe haberse marcado automáticamente como INTERRUPTED
        sess_details = svc_b.get_session(session_id)
        self.assertTrue(sess_details["ok"])
        self.assertEqual(sess_details["status"], "INTERRUPTED")
        self.assertEqual(sess_details["final_verdict"], "INTERRUPTED")

    def test_trading_integration_in_report(self):
        self.svc.start_session("72h")
        report = self.svc.get_validation_report()
        
        self.assertIn("trading_telemetry", report)
        tt = report["trading_telemetry"]
        self.assertEqual(tt["signals_generated"], 1)
        self.assertEqual(tt["trades_executed"], 1)
        self.assertEqual(tt["orders_rejected"], 1)
        self.assertEqual(tt["fill_rate_pct"], 50.0)
        self.assertGreaterEqual(tt["max_drawdown_pct"], 0.0)

    def test_automated_mt5_downtime_tracking(self):
        self.svc.start_session("24h")
        t_disc = datetime(2026, 7, 28, 12, 0, 0, tzinfo=timezone.utc)
        t_recon = datetime(2026, 7, 28, 12, 0, 15, tzinfo=timezone.utc)

        self.svc.notify_mt5_disconnect(t_disc)
        self.svc.notify_mt5_reconnect(t_recon)

        report = self.svc.get_validation_report()
        resil = report["resilience_telemetry"]
        self.assertEqual(resil["reconnections_total"], 1)
        self.assertEqual(resil["downtime_total_seconds"], 15.0)

    def test_forward_validation_score(self):
        score_perfect = self.svc.calculate_forward_score(
            memory_slope=0.0, downtime_sec=0.0, fill_rate_pct=100.0, max_dd_pct=0.0
        )
        self.assertEqual(score_perfect, 100.0)

        score_degraded = self.svc.calculate_forward_score(
            memory_slope=10.0, downtime_sec=120.0, fill_rate_pct=70.0, max_dd_pct=4.0
        )
        self.assertLess(score_degraded, 100.0)
        self.assertGreaterEqual(score_degraded, 0.0)

    def test_historical_session_explorer(self):
        res1 = self.svc.start_session("24h")
        id1 = res1["session_id"]
        self.svc.stop_session("COMPLETED")

        res2 = self.svc.start_session("7d")
        id2 = res2["session_id"]
        self.svc.stop_session("COMPLETED")

        sessions = self.svc.list_sessions()
        self.assertGreaterEqual(len(sessions), 2)
        sess_ids = [s["session_id"] for s in sessions]
        self.assertIn(id1, sess_ids)
        self.assertIn(id2, sess_ids)

        details = self.svc.get_session(id1)
        self.assertTrue(details["ok"])
        self.assertEqual(details["session_id"], id1)

    def test_long_forward_validation_service_singleton(self):
        svc = get_long_forward_validation_service(db_path=self.db_path)
        self.assertIsNotNone(svc)
        status = svc.get_validation_report()
        self.assertIn("forward_validation_score", status)


if __name__ == "__main__":
    unittest.main()
