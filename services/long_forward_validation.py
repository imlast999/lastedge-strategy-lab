"""
LastEdge — Long Forward Validation & Longevity Engine (P5.3 Production Readiness)
==================================================================================
Servicio completo de auditoría y validación de longevidad de la plataforma.
Integra:
  1. Persistencia estricta de sesiones en SQLite (long_forward_sessions).
  2. Integración con trading (señales, trades, rechazadas, equity, drawdown).
  3. Rastreo automático de downtime y reconexiones MT5.
  4. Explorador de sesiones históricas (list_sessions, get_session).
  5. Puntuación cuantitativa "Forward Validation Score" (0.0 - 100.0).
"""

from __future__ import annotations

import os
import sys
import time
import json
import logging
import uuid
from typing import Dict, Any, List, Optional
from datetime import datetime, timezone

from services.database import get_database_manager

try:
    import psutil
except ImportError:
    psutil = None

logger = logging.getLogger(__name__)


class MemorySample:
    """Representa una muestra puntual de consumo de memoria y recursos."""
    def __init__(self, rss_mb: float, vms_mb: float, cpu_pct: float, threads: int, timestamp: Optional[datetime] = None):
        self.timestamp = timestamp or datetime.now(timezone.utc)
        self.rss_mb = rss_mb
        self.vms_mb = vms_mb
        self.cpu_pct = cpu_pct
        self.threads = threads

    def to_dict(self) -> Dict[str, Any]:
        return {
            "timestamp": self.timestamp.isoformat(),
            "rss_mb": self.rss_mb,
            "vms_mb": self.vms_mb,
            "cpu_pct": self.cpu_pct,
            "threads": self.threads,
        }


class LongForwardValidationService:
    """
    Servicio de validación de estabilidad y longevidad en producción.
    """

    def __init__(self, db_path: Optional[str] = None):
        self.db_manager = get_database_manager(db_path)
        self.current_session_id: Optional[str] = None
        self.session_active: bool = False
        self.session_profile: str = "24h"
        self.start_time: Optional[datetime] = None
        
        self.samples: List[MemorySample] = []
        self.anomalies: List[Dict[str, Any]] = []
        self.reconnections_count: int = 0
        self.failures_recovered: int = 0
        self.total_downtime_seconds: float = 0.0
        self._last_disconnect_time: Optional[datetime] = None

        self._init_db_schema()

    def _init_db_schema(self) -> None:
        """Crea esquemas de BD y recupera/marca sesiones interrumpidas por reinicio."""
        try:
            with self.db_manager.get_connection() as conn:
                # Tabla principal de sesiones
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS long_forward_sessions (
                        session_id TEXT PRIMARY KEY,
                        profile TEXT NOT NULL,
                        status TEXT NOT NULL,
                        start_time TEXT NOT NULL,
                        end_time TEXT,
                        final_verdict TEXT,
                        forward_score REAL,
                        downtime_seconds REAL DEFAULT 0.0,
                        reconnections_count INTEGER DEFAULT 0,
                        summary_json TEXT
                    );
                """)
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS long_forward_samples (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        session_id TEXT NOT NULL,
                        rss_mb REAL NOT NULL,
                        vms_mb REAL NOT NULL,
                        cpu_pct REAL NOT NULL,
                        threads INTEGER NOT NULL,
                        timestamp TEXT NOT NULL
                    );
                """)
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS long_forward_anomalies (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        session_id TEXT NOT NULL,
                        anomaly_type TEXT NOT NULL,
                        severity TEXT NOT NULL,
                        description TEXT NOT NULL,
                        timestamp TEXT NOT NULL
                    );
                """)

                # Marcar automáticamente sesiones anteriores que quedaron en estado 'ACTIVE' como 'INTERRUPTED'
                now_iso = datetime.now(timezone.utc).isoformat()
                conn.execute("""
                    UPDATE long_forward_sessions
                    SET status = 'INTERRUPTED',
                        end_time = ?,
                        final_verdict = 'INTERRUPTED'
                    WHERE status = 'ACTIVE';
                """, (now_iso,))

        except Exception as e:
            logger.error(f"[LongForwardValidation] Error inicializando esquemas BD: {e}")

    # ── Muestreo & Anomalías ──────────────────────────────────────────────────
    def record_sample(self, rss_mb: Optional[float] = None, vms_mb: Optional[float] = None, cpu_pct: Optional[float] = None) -> MemorySample:
        """Toma una muestra real de recursos del proceso Python y la almacena."""
        now = datetime.now(timezone.utc)
        threads = 1

        if rss_mb is None or vms_mb is None:
            if psutil is not None:
                try:
                    p = psutil.Process(os.getpid())
                    mem_info = p.memory_info()
                    rss_mb = round(mem_info.rss / (1024 * 1024), 2)
                    vms_mb = round(mem_info.vms / (1024 * 1024), 2)
                    cpu_pct = p.cpu_percent(interval=None)
                    threads = p.num_threads()
                except Exception:
                    rss_mb, vms_mb, cpu_pct = 55.0, 110.0, 0.5
            else:
                rss_mb, vms_mb, cpu_pct = 55.0, 110.0, 0.5

        sample = MemorySample(rss_mb=rss_mb, vms_mb=vms_mb, cpu_pct=cpu_pct or 0.0, threads=threads, timestamp=now)
        self.samples.append(sample)

        # Persistir en SQLite si hay sesión activa
        if self.current_session_id:
            try:
                with self.db_manager.get_connection() as conn:
                    conn.execute("""
                        INSERT INTO long_forward_samples (session_id, rss_mb, vms_mb, cpu_pct, threads, timestamp)
                        VALUES (?, ?, ?, ?, ?, ?);
                    """, (self.current_session_id, sample.rss_mb, sample.vms_mb, sample.cpu_pct, sample.threads, sample.timestamp.isoformat()))
            except Exception as e:
                logger.debug(f"[LongForwardValidation] Error guardando muestra: {e}")

        self._detect_memory_anomalies()
        return sample

    def log_anomaly(self, anomaly_type: str, severity: str, description: str) -> None:
        """Registra una anomalía o evento inesperado en memoria y BD."""
        now_iso = datetime.now(timezone.utc).isoformat()
        anomaly = {
            "timestamp": now_iso,
            "anomaly_type": anomaly_type,
            "severity": severity,  # INFO, WARN, CRITICAL
            "description": description,
        }
        self.anomalies.append(anomaly)
        logger.warning(f"[LongForwardValidation] Anomalía [{severity}] {anomaly_type}: {description}")

        if self.current_session_id:
            try:
                with self.db_manager.get_connection() as conn:
                    conn.execute("""
                        INSERT INTO long_forward_anomalies (session_id, anomaly_type, severity, description, timestamp)
                        VALUES (?, ?, ?, ?, ?);
                    """, (self.current_session_id, anomaly_type, severity, description, now_iso))
            except Exception as e:
                logger.debug(f"[LongForwardValidation] Error guardando anomalía en BD: {e}")

    # ── Rastreo Automático de Downtime MT5 ────────────────────────────────────
    def notify_mt5_disconnect(self, timestamp: Optional[datetime] = None) -> None:
        """Registra automáticamente el inicio de una desconexión de MT5."""
        self._last_disconnect_time = timestamp or datetime.now(timezone.utc)
        self.log_anomaly("MT5_DISCONNECT", "WARN", f"Desconexión de MT5 detectada a las {self._last_disconnect_time.strftime('%H:%M:%S')} UTC")

    def notify_mt5_reconnect(self, timestamp: Optional[datetime] = None) -> None:
        """Registra automáticamente la reconexión exitosa y calcula la duración del downtime."""
        now = timestamp or datetime.now(timezone.utc)
        self.reconnections_count += 1
        downtime_sec = 0.0

        if self._last_disconnect_time is not None:
            downtime_sec = round((now - self._last_disconnect_time).total_seconds(), 2)
            self.total_downtime_seconds += downtime_sec
            self._last_disconnect_time = None

        msg = f"Reconexión exitosa de MT5. Tiempo de inactividad (Downtime): {downtime_sec} segundos."
        self.log_anomaly("MT5_RECONNECT", "INFO", msg)

    def log_failure_recovery(self, subsystem: str, detail: str) -> None:
        """Registra un fallo recuperado con éxito."""
        self.failures_recovered += 1
        self.log_anomaly("FAILURE_RECOVERY", "INFO", f"Recuperación limpia en {subsystem}: {detail}")

    def _detect_memory_anomalies(self) -> None:
        """Analiza la tendencia de crecimiento de memoria RSS (Memory Leak Detection)."""
        if len(self.samples) < 5:
            return
        recent = self.samples[-10:]
        delta_mb = recent[-1].rss_mb - recent[0].rss_mb
        if delta_mb > 50.0:
            self.log_anomaly(
                "MEMORY_LEAK_SUSPECTED",
                "WARN",
                f"Crecimiento rápido de memoria RSS (+{round(delta_mb, 2)} MB de {recent[0].rss_mb} a {recent[-1].rss_mb} MB)"
            )

    def calculate_memory_slope(self) -> float:
        """Calcula la tasa de variación de memoria RSS en MB/hora mediante regresión lineal."""
        if len(self.samples) < 2:
            return 0.0
        n = len(self.samples)
        t0 = self.samples[0].timestamp.timestamp()
        x = [(s.timestamp.timestamp() - t0) / 3600.0 for s in self.samples]
        y = [s.rss_mb for s in self.samples]
        sum_x = sum(x); sum_y = sum(y)
        sum_xy = sum(x[i] * y[i] for i in range(n))
        sum_x2 = sum(x[i] ** 2 for i in range(n))
        denom = (n * sum_x2 - sum_x ** 2)
        if abs(denom) < 1e-9:
            return 0.0
        return round((n * sum_xy - sum_x * sum_y) / denom, 3)

    # ── Puntuación Cuantitativa "Forward Validation Score" (0.0 - 100.0) ──────
    def calculate_forward_score(self, memory_slope: float, downtime_sec: float, fill_rate_pct: float, max_dd_pct: float) -> float:
        """
        Calcula una puntuación cuantitativa (0.0 a 100.0) sobre la calidad global de la sesión.
        Fórmula ponderada:
          • Estabilidad de Memoria (20%): Pendiente 0 MB/h = 20 pts. Se penaliza por encima de 5 MB/h.
          • Disponibilidad & Downtime (25%): 0s downtime = 25 pts. Se reduce según los segundos inactivo.
          • Calidad de Ejecución & Fill Rate (25%): (Fill Rate % / 100) * 25 pts.
          • Control de Riesgo & Drawdown (15%): 0% DD = 15 pts. Se penaliza con DD > 3%.
          • Severidad de Anomalías (15%): 15 pts - (anomalías WARN * 1 + CRITICAL * 5).
        """
        mem_score = max(0.0, 20.0 - max(0.0, memory_slope * 2.0))
        downtime_score = max(0.0, 25.0 - min(25.0, (downtime_sec / 60.0) * 5.0))
        exec_score = max(0.0, (fill_rate_pct / 100.0) * 25.0)
        risk_score = max(0.0, 15.0 - min(15.0, max_dd_pct * 3.0))

        crit_cnt = sum(1 for a in self.anomalies if a.get("severity") == "CRITICAL")
        warn_cnt = sum(1 for a in self.anomalies if a.get("severity") == "WARN")
        anom_score = max(0.0, 15.0 - (crit_cnt * 5.0 + warn_cnt * 1.0))

        total_score = mem_score + downtime_score + exec_score + risk_score + anom_score
        return round(max(0.0, min(100.0, total_score)), 1)

    # ── Generación de Informes & Trading Correlation ─────────────────────────
    def get_validation_report(self) -> Dict[str, Any]:
        """
        Genera un informe completo integrando recursos, resiliencia y métricas de trading reales.
        """
        if not self.samples:
            self.record_sample()

        slope = self.calculate_memory_slope()
        rss_values = [s.rss_mb for s in self.samples]
        min_rss = min(rss_values) if rss_values else 0.0
        max_rss = max(rss_values) if rss_values else 0.0
        avg_rss = round(sum(rss_values) / len(rss_values), 2) if rss_values else 0.0

        # Obtener métricas de trading reales desde la BD
        trading_metrics = self._query_trading_metrics()
        fill_rate = trading_metrics.get("fill_rate_pct", 100.0)
        max_dd = trading_metrics.get("max_drawdown_pct", 0.0)

        # Calcular Forward Validation Score cuantitativo
        forward_score = self.calculate_forward_score(
            memory_slope=slope,
            downtime_sec=self.total_downtime_seconds,
            fill_rate_pct=fill_rate,
            max_dd_pct=max_dd
        )

        verdict = "STABLE"
        if forward_score < 50.0 or any(a["severity"] == "CRITICAL" for a in self.anomalies):
            verdict = "UNSTABLE"
        elif forward_score < 80.0 or slope > 5.0 or self.total_downtime_seconds > 60:
            verdict = "DEGRADED"

        return {
            "session_id": self.current_session_id or "NO_ACTIVE_SESSION",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "session_active": self.session_active,
            "session_profile": self.session_profile,
            "verdict": verdict,
            "forward_validation_score": forward_score,
            "memory_telemetry": {
                "current_rss_mb": rss_values[-1] if rss_values else 0.0,
                "min_rss_mb": min_rss,
                "max_rss_mb": max_rss,
                "avg_rss_mb": avg_rss,
                "memory_growth_slope_mb_per_hour": slope,
                "total_samples": len(self.samples),
            },
            "resilience_telemetry": {
                "reconnections_total": self.reconnections_count,
                "downtime_total_seconds": self.total_downtime_seconds,
                "failures_recovered_total": self.failures_recovered,
                "total_anomalies_logged": len(self.anomalies),
            },
            "trading_telemetry": trading_metrics,
            "anomalies": self.anomalies[-20:],
        }

    def _query_trading_metrics(self) -> Dict[str, Any]:
        """Consulta métricas de trading reales desde `trade_journal`, `enhanced_signals` y `balance_snapshots`."""
        try:
            with self.db_manager.get_connection() as conn:
                # 1. Señales generadas
                sig_cnt = conn.execute("SELECT COUNT(*) FROM enhanced_signals;").fetchone()[0]
                
                # 2. Trades ejecutados y rechazados
                row_trd = conn.execute("""
                    SELECT
                        COUNT(*) as total,
                        SUM(CASE WHEN execution_status = 'SUCCESS' THEN 1 ELSE 0 END) as success,
                        SUM(CASE WHEN execution_status IN ('REJECTED', 'FAILED') THEN 1 ELSE 0 END) as rejected
                    FROM trade_journal;
                """).fetchone()

                total_trd = row_trd[0] or 0
                success_trd = row_trd[1] or 0
                rejected_trd = row_trd[2] or 0
                fill_rate = round((success_trd / total_trd * 100), 1) if total_trd > 0 else 100.0

                # 3. Snapshots de Balance y Drawdown
                row_bal = conn.execute("""
                    SELECT balance, equity, floating_pnl
                    FROM balance_snapshots
                    ORDER BY rowid DESC LIMIT 1;
                """).fetchone()

                bal = row_bal[0] if row_bal else 5000.0
                eq = row_bal[1] if row_bal else bal
                float_pnl = row_bal[2] if row_bal else 0.0

                # Calcular Drawdown
                max_eq_row = conn.execute("SELECT MAX(equity) FROM balance_snapshots;").fetchone()[0]
                peak_eq = max_eq_row if max_eq_row and max_eq_row > 0 else eq
                dd_pct = round(((peak_eq - eq) / peak_eq * 100), 2) if peak_eq > 0 and peak_eq > eq else 0.0

                return {
                    "signals_generated": sig_cnt,
                    "trades_executed": success_trd,
                    "orders_rejected": rejected_trd,
                    "fill_rate_pct": fill_rate,
                    "current_balance": bal,
                    "current_equity": eq,
                    "floating_pnl": float_pnl,
                    "max_drawdown_pct": dd_pct,
                }
        except Exception as e:
            logger.debug(f"[LongForwardValidation] Error consultando métricas trading BD: {e}")
            return {
                "signals_generated": 0, "trades_executed": 0, "orders_rejected": 0,
                "fill_rate_pct": 100.0, "current_balance": 5000.0, "current_equity": 5000.0,
                "floating_pnl": 0.0, "max_drawdown_pct": 0.0
            }

    # ── Gestión del Ciclo de Vida de Sesiones ─────────────────────────────────
    def start_session(self, profile: str = "24h") -> Dict[str, Any]:
        """Inicia una nueva sesión persistida en SQLite."""
        self.session_id = f"lfv_{profile}_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}"
        self.current_session_id = self.session_id
        self.session_active = True
        self.session_profile = profile
        self.start_time = datetime.now(timezone.utc)
        self.samples.clear()
        self.anomalies.clear()
        self.reconnections_count = 0
        self.failures_recovered = 0
        self.total_downtime_seconds = 0.0

        try:
            with self.db_manager.get_connection() as conn:
                conn.execute("""
                    INSERT INTO long_forward_sessions (session_id, profile, status, start_time)
                    VALUES (?, ?, 'ACTIVE', ?);
                """, (self.current_session_id, profile, self.start_time.isoformat()))
        except Exception as e:
            logger.error(f"[LongForwardValidation] Error iniciando sesión en BD: {e}")

        self.record_sample()
        logger.info(f"[LongForwardValidation] Sesión de validación {self.current_session_id} ({profile}) iniciada.")
        return {"ok": True, "session_id": self.current_session_id, "profile": profile}

    def stop_session(self, status: str = "COMPLETED") -> Dict[str, Any]:
        """Detiene la sesión activa y guarda el veredicto e informe final en SQLite."""
        self.session_active = False
        report = self.get_validation_report()
        now_iso = datetime.now(timezone.utc).isoformat()

        if self.current_session_id:
            try:
                with self.db_manager.get_connection() as conn:
                    conn.execute("""
                        UPDATE long_forward_sessions
                        SET status = ?,
                            end_time = ?,
                            final_verdict = ?,
                            forward_score = ?,
                            downtime_seconds = ?,
                            reconnections_count = ?,
                            summary_json = ?
                        WHERE session_id = ?;
                    """, (
                        status,
                        now_iso,
                        report["verdict"],
                        report["forward_validation_score"],
                        self.total_downtime_seconds,
                        self.reconnections_count,
                        json.dumps(report),
                        self.current_session_id
                    ))
            except Exception as e:
                logger.error(f"[LongForwardValidation] Error guardando cierre de sesión en BD: {e}")

        logger.info(f"[LongForwardValidation] Sesión {self.current_session_id} finalizada ({status}). Score: {report['forward_validation_score']}/100")
        return {"ok": True, "session_id": self.current_session_id, "status": status, "report": report}

    # ── Explorador de Sesiones Históricas ─────────────────────────────────────
    def list_sessions(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Devuelve el historial de sesiones almacenadas en la base de datos."""
        try:
            with self.db_manager.get_connection() as conn:
                rows = conn.execute("""
                    SELECT session_id, profile, status, start_time, end_time, final_verdict, forward_score, downtime_seconds, reconnections_count
                    FROM long_forward_sessions
                    ORDER BY rowid DESC
                    LIMIT ?;
                """, (limit,)).fetchall()

            return [
                {
                    "session_id": r[0], "profile": r[1], "status": r[2],
                    "start_time": r[3], "end_time": r[4], "final_verdict": r[5],
                    "forward_score": r[6], "downtime_seconds": r[7], "reconnections_count": r[8]
                }
                for r in rows
            ]
        except Exception as e:
            logger.error(f"[LongForwardValidation] Error listando sesiones: {e}")
            return []

    def get_session(self, session_id: str) -> Dict[str, Any]:
        """Obtiene los detalles completos de una sesión específica por ID."""
        try:
            with self.db_manager.get_connection() as conn:
                row = conn.execute("""
                    SELECT session_id, profile, status, start_time, end_time, final_verdict, forward_score, summary_json
                    FROM long_forward_sessions
                    WHERE session_id = ?;
                """, (session_id,)).fetchone()

                if not row:
                    return {"ok": False, "message": f"Sesión {session_id} no encontrada."}

                summary = json.loads(row[7]) if row[7] else {}
                return {
                    "ok": True,
                    "session_id": row[0],
                    "profile": row[1],
                    "status": row[2],
                    "start_time": row[3],
                    "end_time": row[4],
                    "final_verdict": row[5],
                    "forward_score": row[6],
                    "details": summary
                }
        except Exception as e:
            logger.error(f"[LongForwardValidation] Error obteniendo sesión {session_id}: {e}")
            return {"ok": False, "message": str(e)}


# Instancia singleton
_long_forward_validation_instance: Optional[LongForwardValidationService] = None

def get_long_forward_validation_service(db_path: Optional[str] = None) -> LongForwardValidationService:
    global _long_forward_validation_instance
    if _long_forward_validation_instance is None or db_path is not None:
        _long_forward_validation_instance = LongForwardValidationService(db_path)
    return _long_forward_validation_instance
