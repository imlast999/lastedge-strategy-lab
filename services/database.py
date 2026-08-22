"""
Database Service — LastEdge Strategy Lab
services/database.py

Thread-safe SQLite connection manager in WAL mode for Strategy Lab research runs,
backtest experiments, and candidate registry.
"""

from __future__ import annotations

import os
import sqlite3
import logging
from contextlib import contextmanager
from typing import Generator

logger = logging.getLogger(__name__)

_DEFAULT_DB_PATH = os.getenv(
    "RESEARCH_DB_PATH",
    os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "research.db")
)


class DatabaseManager:
    """Centralized SQLite connection manager for Strategy Lab in WAL mode."""

    def __init__(self, db_path: str = _DEFAULT_DB_PATH):
        self.db_path = db_path
        os.makedirs(os.path.dirname(os.path.abspath(self.db_path)), exist_ok=True)
        self._ensure_wal_mode()

    def _ensure_wal_mode(self) -> None:
        try:
            with sqlite3.connect(self.db_path, timeout=30.0) as conn:
                conn.execute("PRAGMA journal_mode=WAL;")
                conn.execute("PRAGMA busy_timeout=10000;")
                conn.execute("PRAGMA synchronous=NORMAL;")
        except Exception as e:
            logger.warning(f"[DatabaseManager] Failed to set WAL mode on {self.db_path}: {e}")

    @contextmanager
    def get_connection(self) -> Generator[sqlite3.Connection, None, None]:
        conn = sqlite3.connect(self.db_path, timeout=30.0)
        conn.row_factory = sqlite3.Row
        try:
            conn.execute("PRAGMA busy_timeout=10000;")
            yield conn
            conn.commit()
        except Exception as e:
            conn.rollback()
            logger.error(f"[DatabaseManager] SQLite transaction error: {e}")
            raise
        finally:
            conn.close()


_db_managers = {}


def get_database_manager(db_path: str = _DEFAULT_DB_PATH) -> DatabaseManager:
    global _db_managers
    if db_path not in _db_managers:
        _db_managers[db_path] = DatabaseManager(db_path)
    return _db_managers[db_path]
