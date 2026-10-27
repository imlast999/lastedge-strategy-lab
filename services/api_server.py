"""
LastEdge Strategy Lab — REST API Server
services/api_server.py

Provides clean, decoupled REST endpoints for external UI applications (LastEdge App,
Web Dashboard, Mobile App) to query quantitative research experiments, backtest
telemetry, and validated strategy candidates without importing internal Python modules.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

# Ensure Strategy Lab root is at the front of sys.path, and services directory doesn't shadow stdlib
_LAB_ROOT = str(Path(__file__).resolve().parent.parent)
_SERVICES_DIR = str(Path(__file__).resolve().parent)
if sys.path and sys.path[0] == _SERVICES_DIR:
    sys.path.pop(0)
if _LAB_ROOT not in sys.path:
    sys.path.insert(0, _LAB_ROOT)

import json
import logging
import threading
from datetime import datetime, timezone
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)


class ReusableThreadingHTTPServer(ThreadingHTTPServer):
    allow_reuse_address = True


class ResearchAPIHandler(BaseHTTPRequestHandler):
    """HTTP request handler for LastEdge Strategy Lab REST API."""

    def _send_json(self, status_code: int, data: Any):
        try:
            body = json.dumps(data, indent=2, default=str).encode("utf-8")
            self.send_response(status_code)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Connection", "close")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
            self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")
            self.end_headers()
            self.wfile.write(body)
            self.wfile.flush()
        except (ConnectionAbortedError, BrokenPipeError, OSError):
            pass
        except Exception as e:
            logger.error("Error sending JSON response: %s", e)

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")
        self.end_headers()

    def do_GET(self):
        path = self.path.split("?")[0].rstrip("/")

        try:
            # ── Root Index & Discovery ─────────────────────────────────────────
            if path in ("", "/", "/api"):
                self._send_json(200, {
                    "ok": True,
                    "service": "LastEdge Strategy Lab",
                    "version": "1.0.0",
                    "status": "ONLINE",
                    "endpoints": {
                        "health": "/api/health",
                        "status": "/api/research/status",
                        "experiments": "/api/research/experiments",
                        "candidates": "/api/research/candidates",
                        "wfa": "/api/research/wfa",
                        "monte_carlo": "/api/research/monte-carlo"
                    },
                    "timestamp": datetime.now(timezone.utc).isoformat()
                })

            # ── Health & Status ───────────────────────────────────────────────
            elif path in ("/api/research/health", "/api/health", "/health"):
                self._send_json(200, {
                    "ok": True,
                    "service": "LastEdge Strategy Lab",
                    "status": "HEALTHY",
                    "timestamp": datetime.now(timezone.utc).isoformat()
                })

            elif path in ("/api/research/status", "/api/status"):
                from services.research_store import get_research_store
                from services.promotion import get_promotion_service
                store = get_research_store()
                candidates = get_promotion_service().list_candidates()
                _, total_exps = store.list_experiments(limit=1)

                self._send_json(200, {
                    "ok": True,
                    "service": "LastEdge Strategy Lab",
                    "status": "ONLINE",
                    "total_experiments": total_exps,
                    "candidate_strategies_count": len(candidates),
                    "timestamp": datetime.now(timezone.utc).isoformat()
                })

            # ── Experiments & Research Store ──────────────────────────────────
            elif path in ("/api/research/experiments", "/api/experiments"):
                import urllib.parse
                from services.research_store import get_research_store
                store = get_research_store()
                
                parsed_url = urllib.parse.urlparse(self.path)
                qs = urllib.parse.parse_qs(parsed_url.query)
                exp_type = qs.get("type", [None])[0]
                sym_filter = qs.get("symbol", [None])[0]
                strat_filter = qs.get("strategy", [None])[0]
                limit_val = int(qs.get("limit", [100])[0])

                exps, total = store.list_experiments(
                    symbol=sym_filter,
                    strategy=strat_filter,
                    experiment_type=exp_type,
                    limit=limit_val
                )

                backtests = [e for e in exps if str(e.get("experiment_id", "")).startswith("bt_")]
                research_list = [e for e in exps if not str(e.get("experiment_id", "")).startswith("bt_")]

                self._send_json(200, {
                    "ok": True,
                    "experiments": exps,
                    "backtests": backtests,
                    "research": research_list,
                    "total": total
                })

            # ── Strategy Candidates ───────────────────────────────────────────
            elif path in ("/api/research/candidates", "/api/candidates"):
                from services.promotion import get_promotion_service
                candidates = get_promotion_service().list_candidates()
                self._send_json(200, {
                    "ok": True,
                    "candidates": candidates,
                    "count": len(candidates)
                })

            # ── Available Strategies Registry ─────────────────────────────────
            elif path in ("/api/research/strategies", "/api/strategies"):
                from core.strategy_catalog import get_strategy_catalog
                self._send_json(200, get_strategy_catalog())

            # ── Single Experiment Detail or Reopen ────────────────────────────
            elif path.startswith("/api/research/experiments/") or path.startswith("/api/experiments/"):
                parts = path.split("/")
                exp_id = parts[4] if path.startswith("/api/research/experiments/") else parts[3]
                from services.research_store import get_research_store
                store = get_research_store()
                if path.endswith("/reopen"):
                    payload = store.get_reopen_payload(exp_id)
                    if payload:
                        self._send_json(200, {"ok": True, "reproducible_payload": payload})
                    else:
                        self._send_json(404, {"ok": False, "error": f"Experiment '{exp_id}' not found."})
                else:
                    exp = store.get_experiment(exp_id)
                    if exp:
                        self._send_json(200, {"ok": True, "experiment": exp})
                    else:
                        self._send_json(404, {"ok": False, "error": f"Experiment '{exp_id}' not found."})

            else:
                self._send_json(404, {"ok": False, "error": f"Endpoint '{self.path}' not found on Strategy Lab API."})

        except Exception as e:
            logger.error("API error handling GET %s: %s", self.path, e)
            self._send_json(500, {"ok": False, "error": str(e)})

    def do_PATCH(self):
        self.do_POST()

    def do_POST(self):
        path = self.path.split("?")[0].rstrip("/")

        try:
            content_length = int(self.headers.get("Content-Length", 0))
            body_data = {}
            if content_length > 0:
                raw_body = self.rfile.read(content_length).decode("utf-8")
                body_data = json.loads(raw_body) if raw_body else {}

            if path in ("/api/research/promote", "/api/promote"):
                candidate_id = body_data.get("candidate_id")
                approver = body_data.get("approver", "Architect")
                if not candidate_id:
                    self._send_json(400, {"ok": False, "error": "Missing 'candidate_id' parameter."})
                    return

                from services.promotion import get_promotion_service
                res = get_promotion_service().promote_to_production(candidate_id=candidate_id, approver=approver)
                self._send_json(200 if res.get("ok") else 400, res)

            elif path in ("/api/research/backtest", "/api/backtest"):
                from services.backtest_service import get_backtest_service
                symbol = body_data.get("symbol", "EURUSD")
                strategy = body_data.get("strategy")
                timeframe = body_data.get("timeframe", "H1")
                bars = int(body_data.get("bars", 5000))
                sl_pips = float(body_data["sl_pips"]) if body_data.get("sl_pips") is not None else None
                tp_pips = float(body_data["tp_pips"]) if body_data.get("tp_pips") is not None else None

                t_start = datetime.now()
                now_str = t_start.strftime("%Y-%m-%d %H:%M:%S")
                print(f"[{now_str}] [Strategy Lab] 🚀 INICIANDO BACKTEST: {symbol} | {strategy or 'default'} | {timeframe} | {bars} bars...")
                sys.stdout.flush()

                svc = get_backtest_service()
                report = svc.run_backtest(
                    symbol=symbol,
                    strategy_name=strategy,
                    timeframe=timeframe,
                    bars=bars,
                    sl_pips=sl_pips,
                    tp_pips=tp_pips,
                )
                elapsed = (datetime.now() - t_start).total_seconds()
                trades = report.get("signals", {}).get("total", 0) if report.get("ok") else 0
                verdict = report.get("verdict", {}).get("badge", "ERR") if report.get("ok") else "FAILED"
                print(f"[{now_str}] [Strategy Lab] 🏁 BACKTEST FINALIZADO: {symbol} | {strategy or 'default'} in {elapsed:.2f}s | trades={trades} | verdict={verdict}")
                sys.stdout.flush()

                self._send_json(200 if report.get("ok") else 400, report)

            elif path in ("/api/research/run", "/api/research/research", "/api/research"):
                from services.research_service import get_research_service
                symbol = body_data.get("symbol", "EURUSD")
                strategy = body_data.get("strategy")
                timeframe = body_data.get("timeframe", "H1")
                bars = int(body_data.get("bars", 10000))
                n_sims = int(body_data.get("n_simulations", 2000))

                t_start = datetime.now()
                now_str = t_start.strftime("%Y-%m-%d %H:%M:%S")
                print(f"[{now_str}] [Strategy Lab] 🔬 INICIANDO RESEARCH: {symbol} | {strategy or 'default'} | {timeframe} | {bars} bars | {n_sims} MC...")
                sys.stdout.flush()

                svc = get_research_service()
                report = svc.run_research(
                    symbol=symbol,
                    strategy_name=strategy,
                    timeframe=timeframe,
                    bars=bars,
                    n_simulations=n_sims,
                )
                elapsed = (datetime.now() - t_start).total_seconds()
                stability = report.get("stability_score", 0.0) if report.get("ok") else 0.0
                rating = report.get("stability_rating", "ERR") if report.get("ok") else "FAILED"
                print(f"[{now_str}] [Strategy Lab] 🏁 RESEARCH FINALIZADO: {symbol} in {elapsed:.2f}s | Stability={stability} | Rating={rating}")
                sys.stdout.flush()

                self._send_json(200 if report.get("ok") else 400, report)

            elif path.startswith("/api/research/experiments/") or path.startswith("/api/experiments/"):
                parts = path.split("/")
                exp_id = parts[4] if path.startswith("/api/research/experiments/") else parts[3]
                from services.research_store import get_research_store
                store = get_research_store()
                ok = store.update_experiment(exp_id, body_data)
                self._send_json(200 if ok else 400, {"ok": ok, "experiment_id": exp_id})

            else:
                self._send_json(404, {"ok": False, "error": f"POST endpoint '{self.path}' not found."})

        except Exception as e:
            logger.error("API error handling POST %s: %s", self.path, e)
            self._send_json(500, {"ok": False, "error": str(e)})

    def log_message(self, format, *args):
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        msg = format % args
        print(f"[{now_str}] [Strategy Lab] {msg}")
        sys.stdout.flush()


class ResearchAPIServer:
    """Manages the background HTTP server for Strategy Lab REST API."""

    def __init__(self, host: str = "0.0.0.0", port: Optional[int] = None):
        self.host = host or os.getenv("RESEARCH_API_HOST", "0.0.0.0")
        self.port = port or int(os.getenv("RESEARCH_API_PORT", "8082"))
        self.server: Optional[ReusableThreadingHTTPServer] = None
        self.thread: Optional[threading.Thread] = None
        self.is_running = False
        self.lock = threading.Lock()

    def start(self):
        with self.lock:
            if self.is_running:
                return
            try:
                self.server = ReusableThreadingHTTPServer((self.host, self.port), ResearchAPIHandler)
                self.is_running = True
                self.thread = threading.Thread(target=self.server.serve_forever, daemon=True, name="ResearchAPIServer")
                self.thread.start()
                logger.info("[Research API] Server listening on http://%s:%d", self.host, self.port)
            except Exception as e:
                logger.error("[Research API] Failed to start server on port %d: %s", self.port, e)

    def stop(self):
        with self.lock:
            if not self.is_running or not self.server:
                return
            self.is_running = False
            try:
                self.server.shutdown()
                self.server.server_close()
                logger.info("[Research API] Server stopped.")
            except Exception as e:
                logger.debug("[Research API] Error during shutdown: %s", e)


_api_server_instance: Optional[ResearchAPIServer] = None


def get_research_api_server(port: Optional[int] = None) -> ResearchAPIServer:
    global _api_server_instance
    if _api_server_instance is None:
        _api_server_instance = ResearchAPIServer(port=port)
    return _api_server_instance


def start_research_api_server(port: Optional[int] = None) -> ResearchAPIServer:
    srv = get_research_api_server(port=port)
    srv.start()
    return srv


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s  %(levelname)-7s  %(message)s")
    port = int(sys.argv[1]) if len(sys.argv) > 1 else int(os.getenv("RESEARCH_API_PORT", "8082"))
    srv = start_research_api_server(port=port)
    print("=" * 65)
    print(f"🔬 LastEdge Strategy Lab — REST API Server (: {port})")
    print("=" * 65)
    print(f"📡 API escuchando en http://localhost:{port}")
    print("   Endpoints de Investigación Cuantitativa:")
    print(f"   • http://localhost:{port}/api/health")
    print(f"   • http://localhost:{port}/api/research/status")
    print(f"   • http://localhost:{port}/api/research/strategies")
    print(f"   • http://localhost:{port}/api/research/experiments")
    print(f"   • http://localhost:{port}/api/research/backtest (POST)")
    print("=" * 65)
    print("Presiona Ctrl+C para detener el servicio.\n")
    sys.stdout.flush()

    try:
        import time
        counter = 0
        while True:
            time.sleep(1)
            counter += 1
            if counter % 15 == 0:
                now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                print(f"[{now_str}] [Strategy Lab] 💓 Heartbeat OK | API :8082 activa | Research Store listo")
                sys.stdout.flush()
    except KeyboardInterrupt:
        print("\n🛑 Deteniendo Strategy Lab API...")
        sys.stdout.flush()
        srv.stop()

