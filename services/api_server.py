"""
LastEdge Strategy Lab — REST API Server
services/api_server.py

Provides clean, decoupled REST endpoints for external UI applications (LastEdge App,
Web Dashboard, Mobile App) to query quantitative research experiments, backtest
telemetry, and validated strategy candidates without importing internal Python modules.
"""

from __future__ import annotations

import json
import logging
import os
import sys
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
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
            self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")
            self.end_headers()
            self.wfile.write(body)
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
            # ── Health & Status ───────────────────────────────────────────────
            if path in ("/api/research/health", "/api/health", "/health"):
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
                from services.research_store import get_research_store
                store = get_research_store()
                exps, total = store.list_experiments(limit=50)
                self._send_json(200, {
                    "ok": True,
                    "experiments": exps,
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

            else:
                self._send_json(404, {"ok": False, "error": f"Endpoint '{self.path}' not found on Strategy Lab API."})

        except Exception as e:
            logger.error("API error handling GET %s: %s", self.path, e)
            self._send_json(500, {"ok": False, "error": str(e)})

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

            else:
                self._send_json(404, {"ok": False, "error": f"POST endpoint '{self.path}' not found."})

        except Exception as e:
            logger.error("API error handling POST %s: %s", self.path, e)
            self._send_json(500, {"ok": False, "error": str(e)})

    def log_message(self, format, *args):
        pass


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
    print(f"Strategy Lab API Server running on port {port}. Press Ctrl+C to stop.")
    try:
        import time
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        srv.stop()
