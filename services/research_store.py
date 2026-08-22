"""
Research Store — services/research_store.py

Servicio centralizado de persistencia y trazabilidad de investigaciones cuantitativas (Research Database).
Registra metadatos completos, hipótesis, configuración reproducible (JSON), versión del bot,
commit de Git, métricas estadísticas, etiquetas y decisiones científicas (DRAFT, CANDIDATE, PROMOTED, REJECTED).
"""

import json
import logging
import os
import sqlite3
import subprocess
from datetime import datetime, timezone
from contextlib import contextmanager
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

_DEFAULT_DB = os.getenv(
    'RESEARCH_DB_PATH',
    os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'data', 'research.db')
)
_DEFAULT_RESULTS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'backtest_results', 'exit_research')

def get_git_commit_hash() -> str:
    """Obtiene el hash del commit actual de Git para garantizar trazabilidad exacta del código."""
    try:
        repo_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        out = subprocess.check_output(
            ['git', 'rev-parse', 'HEAD'],
            cwd=repo_dir,
            stderr=subprocess.DEVNULL
        ).decode('utf-8').strip()
        return out
    except Exception:
        return 'unknown'

class ResearchStore:
    """
    Gestor de persistencia SQLite para la base de datos de investigaciones de LastEdge.
    """

    def __init__(self, db_path: str = _DEFAULT_DB, results_dir: str = _DEFAULT_RESULTS_DIR):
        self.db_path = db_path
        self.results_dir = results_dir
        self.ensure_tables()
        self.auto_ingest_filesystem_runs()

    @contextmanager
    def _get_conn(self):
        from services.database import get_database_manager
        with get_database_manager(self.db_path).get_connection() as conn:
            yield conn

    def ensure_tables(self) -> None:
        """Crea la tabla research_experiments y sus índices si no existen."""
        try:
            with self._get_conn() as conn:
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS research_experiments (
                        id                      INTEGER PRIMARY KEY AUTOINCREMENT,
                        experiment_id           TEXT UNIQUE NOT NULL,
                        title                   TEXT NOT NULL,
                        hypothesis              TEXT,
                        symbol                  TEXT NOT NULL,
                        strategy                TEXT NOT NULL,
                        timeframe               TEXT DEFAULT 'H1',
                        bars_count              INTEGER DEFAULT 20000,
                        data_start_date         TEXT,
                        data_end_date           TEXT,
                        bot_version             TEXT DEFAULT '1.1.0',
                        git_commit              TEXT,
                        environment_meta        TEXT,
                        config_json             TEXT NOT NULL,
                        status                  TEXT NOT NULL DEFAULT 'COMPLETED',
                        decision_status         TEXT DEFAULT 'DRAFT',
                        decision_notes          TEXT,
                        tags                    TEXT,
                        notes                   TEXT,
                        best_variant            TEXT,
                        best_profit_factor      REAL,
                        best_winrate            REAL,
                        best_stability_score    REAL,
                        best_max_drawdown       REAL,
                        best_sharpe             REAL,
                        best_sortino            REAL,
                        best_calmar             REAL,
                        best_mc_ruin_pct        REAL,
                        wf_stability            REAL,
                        metrics_json            TEXT,
                        artifacts_path          TEXT,
                        created_at              TEXT DEFAULT (datetime('now')),
                        updated_at              TEXT DEFAULT (datetime('now'))
                    )
                """)
                # Índices para búsquedas de alto rendimiento
                conn.execute("CREATE INDEX IF NOT EXISTS idx_exp_symbol ON research_experiments(symbol)")
                conn.execute("CREATE INDEX IF NOT EXISTS idx_exp_strategy ON research_experiments(strategy)")
                conn.execute("CREATE INDEX IF NOT EXISTS idx_exp_decision ON research_experiments(decision_status)")
                conn.execute("CREATE INDEX IF NOT EXISTS idx_exp_created ON research_experiments(created_at DESC)")
                conn.commit()
        except Exception as e:
            logger.error(f"[ResearchStore] Error creando esquema de BD: {e}")

    def auto_ingest_filesystem_runs(self) -> int:
        """
        Escanea la carpeta backtest_results/exit_research/ e ingesta automáticamente
        las corridas históricas en la base de datos de investigación si aún no existen.
        """
        if not os.path.exists(self.results_dir):
            return 0

        ingested_count = 0
        try:
            entries = os.listdir(self.results_dir)
            for entry in sorted(entries):
                run_dir = os.path.join(self.results_dir, entry)
                if not os.path.isdir(run_dir):
                    continue

                summary_file = os.path.join(run_dir, 'summary.json')
                if not os.path.exists(summary_file):
                    continue

                exp_id = entry
                # Verificar si ya existe en la BD
                with self._get_conn() as conn:
                    existing = conn.execute(
                        "SELECT id FROM research_experiments WHERE experiment_id = ?",
                        (exp_id,)
                    ).fetchone()
                    if existing:
                        continue

                # Leer summary.json
                try:
                    with open(summary_file, 'r', encoding='utf-8') as f:
                        summary_data = json.load(f)

                    symbol = summary_data.get('symbol', 'UNKNOWN')
                    strategy = f"{symbol.lower()}_partial"
                    best = summary_data.get('comparison_table', [{}])[0] if summary_data.get('comparison_table') else {}
                    gen_at = summary_data.get('generated_at') or datetime.now(timezone.utc).isoformat()

                    config_payload = {
                        "symbol": symbol,
                        "strategy": strategy,
                        "validation_mode": summary_data.get('validation_mode', 'no_optimization'),
                        "run_id": exp_id,
                        "source": "auto_ingested_filesystem"
                    }

                    title = f"Exit Research {symbol} ({exp_id})"
                    hypothesis = f"Evaluación cuantitativa de 13 variantes de salida para {symbol}."

                    self.create_experiment({
                        "experiment_id": exp_id,
                        "title": title,
                        "hypothesis": hypothesis,
                        "symbol": symbol,
                        "strategy": strategy,
                        "timeframe": "H1",
                        "bars_count": 20000,
                        "bot_version": "1.1.0",
                        "git_commit": get_git_commit_hash(),
                        "environment_meta": json.dumps({"os": os.name, "ingestion": "auto"}),
                        "config_json": json.dumps(config_payload, ensure_ascii=False),
                        "status": "COMPLETED",
                        "decision_status": "DRAFT",
                        "decision_notes": "Ingestado automáticamente desde artefactos históricos.",
                        "tags": json.dumps(["exit-research", symbol.lower(), "historical"]),
                        "notes": summary_data.get('conclusions', {}).get('summary', 'Sin notas adicionales.'),
                        "best_variant": best.get('variant', 'N/A'),
                        "best_profit_factor": float(best.get('profit_factor', 0.0)),
                        "best_winrate": float(best.get('winrate', 0.0)),
                        "best_stability_score": float(best.get('stability_score', 0.0)),
                        "best_max_drawdown": float(best.get('max_drawdown', 0.0)),
                        "best_sharpe": float(best.get('sharpe', 0.0)),
                        "metrics_json": json.dumps(summary_data, ensure_ascii=False),
                        "artifacts_path": run_dir,
                        "created_at": gen_at,
                    })
                    ingested_count += 1
                except Exception as ingest_err:
                    logger.warning(f"[ResearchStore] Error ingestando {exp_id}: {ingest_err}")

        except Exception as e:
            logger.error(f"[ResearchStore] Error durante auto_ingest: {e}")

        if ingested_count > 0:
            logger.info(f"[ResearchStore] Ingestadas {ingested_count} investigaciones históricas en SQLite.")
        return ingested_count

    def create_experiment(self, exp_data: Dict[str, Any]) -> str:
        """
        Registra una nueva investigación en la Research Database con trazabilidad completa.
        """
        now_iso = datetime.now(timezone.utc).isoformat()
        exp_id = exp_data.get('experiment_id') or f"exp_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}"

        title = exp_data.get('title') or f"Investigación {exp_data.get('symbol', 'GENERIC')}"
        hypothesis = exp_data.get('hypothesis', '')
        symbol = str(exp_data.get('symbol', 'UNKNOWN')).upper()
        strategy = str(exp_data.get('strategy', 'unknown')).lower()
        timeframe = exp_data.get('timeframe', 'H1')
        bars_count = int(exp_data.get('bars_count', 20000))
        data_start_date = exp_data.get('data_start_date', '')
        data_end_date = exp_data.get('data_end_date', '')
        bot_version = exp_data.get('bot_version', '1.1.0')
        git_commit = exp_data.get('git_commit') or get_git_commit_hash()
        env_meta = exp_data.get('environment_meta') or json.dumps({"python_version": os.sys.version.split()[0]})

        config_obj = exp_data.get('config') or exp_data.get('config_json') or {}
        config_json = config_obj if isinstance(config_obj, str) else json.dumps(config_obj, ensure_ascii=False)

        status = exp_data.get('status', 'COMPLETED')
        decision_status = exp_data.get('decision_status', 'DRAFT')
        decision_notes = exp_data.get('decision_notes', '')

        tags = exp_data.get('tags', [])
        tags_json = tags if isinstance(tags, str) else json.dumps(tags, ensure_ascii=False)

        notes = exp_data.get('notes', '')
        best_variant = exp_data.get('best_variant', '')
        best_pf = float(exp_data.get('best_profit_factor') or 0.0)
        best_wr = float(exp_data.get('best_winrate') or 0.0)
        best_stab = float(exp_data.get('best_stability_score') or 0.0)
        best_dd = float(exp_data.get('best_max_drawdown') or 0.0)
        best_sharpe = float(exp_data.get('best_sharpe') or 0.0)
        best_sortino = float(exp_data.get('best_sortino') or 0.0)
        best_calmar = float(exp_data.get('best_calmar') or 0.0)
        best_ruin = float(exp_data.get('best_mc_ruin_pct') or 0.0)
        wf_stab = float(exp_data.get('wf_stability') or 0.0)

        metrics_obj = exp_data.get('metrics') or exp_data.get('metrics_json') or {}
        metrics_json = metrics_obj if isinstance(metrics_obj, str) else json.dumps(metrics_obj, ensure_ascii=False)

        artifacts_path = exp_data.get('artifacts_path', '')
        created_at = exp_data.get('created_at', now_iso)

        with self._get_conn() as conn:
            conn.execute("""
                INSERT OR REPLACE INTO research_experiments (
                    experiment_id, title, hypothesis, symbol, strategy, timeframe,
                    bars_count, data_start_date, data_end_date, bot_version, git_commit,
                    environment_meta, config_json, status, decision_status, decision_notes,
                    tags, notes, best_variant, best_profit_factor, best_winrate,
                    best_stability_score, best_max_drawdown, best_sharpe, best_sortino,
                    best_calmar, best_mc_ruin_pct, wf_stability, metrics_json,
                    artifacts_path, created_at, updated_at
                ) VALUES (
                    ?, ?, ?, ?, ?, ?,
                    ?, ?, ?, ?, ?,
                    ?, ?, ?, ?, ?,
                    ?, ?, ?, ?, ?,
                    ?, ?, ?, ?,
                    ?, ?, ?, ?,
                    ?, ?, ?
                )
            """, (
                exp_id, title, hypothesis, symbol, strategy, timeframe,
                bars_count, data_start_date, data_end_date, bot_version, git_commit,
                env_meta, config_json, status, decision_status, decision_notes,
                tags_json, notes, best_variant, best_pf, best_wr,
                best_stab, best_dd, best_sharpe, best_sortino,
                best_calmar, best_ruin, wf_stab, metrics_json,
                artifacts_path, created_at, now_iso
            ))
            conn.commit()

        logger.info(f"[ResearchStore] Experimento registrado: {exp_id} ({symbol} - {strategy})")
        return exp_id

    def update_experiment(self, exp_id: str, updates: Dict[str, Any]) -> bool:
        """
        Actualiza el dictamen científico, hipótesis, notas o etiquetas de un experimento.
        """
        allowed = [
            'title', 'hypothesis', 'decision_status', 'decision_notes',
            'tags', 'notes', 'status', 'best_variant', 'best_profit_factor',
            'best_stability_score'
        ]
        set_clauses = []
        params = []

        for key, val in updates.items():
            if key in allowed:
                set_clauses.append(f"{key} = ?")
                if key == 'tags' and not isinstance(val, str):
                    val = json.dumps(val, ensure_ascii=False)
                params.append(val)

        if not set_clauses:
            return False

        set_clauses.append("updated_at = ?")
        params.append(datetime.now(timezone.utc).isoformat())
        params.append(exp_id)

        try:
            with self._get_conn() as conn:
                cur = conn.execute(
                    f"UPDATE research_experiments SET {', '.join(set_clauses)} WHERE experiment_id = ?",
                    params
                )
                conn.commit()
                return cur.rowcount > 0
        except Exception as e:
            logger.error(f"[ResearchStore] Error actualizando experimento {exp_id}: {e}")
            return False

    def get_experiment(self, exp_id: str) -> Optional[Dict[str, Any]]:
        """Devuelve una ficha de investigación completa."""
        try:
            with self._get_conn() as conn:
                row = conn.execute(
                    "SELECT * FROM research_experiments WHERE experiment_id = ?",
                    (exp_id,)
                ).fetchone()
                if not row:
                    return None
                return self._row_to_dict(row)
        except Exception as e:
            logger.error(f"[ResearchStore] Error consultando experimento {exp_id}: {e}")
            return None

    def list_experiments(
        self,
        symbol: Optional[str] = None,
        strategy: Optional[str] = None,
        decision_status: Optional[str] = None,
        query: Optional[str] = None,
        tag: Optional[str] = None,
        min_pf: Optional[float] = None,
        min_stability: Optional[float] = None,
        sort_by: str = 'created_at',
        order: str = 'DESC',
        limit: int = 50,
        offset: int = 0
    ) -> Tuple[List[Dict[str, Any]], int]:
        """
        Consulta y filtra la Research Database multicriterio.
        """
        conditions = []
        params: list = []

        if symbol:
            conditions.append("symbol = ?")
            params.append(symbol.upper())

        if strategy:
            conditions.append("strategy = ?")
            params.append(strategy.lower())

        if decision_status:
            conditions.append("decision_status = ?")
            params.append(decision_status.upper())

        if min_pf is not None:
            conditions.append("best_profit_factor >= ?")
            params.append(float(min_pf))

        if min_stability is not None:
            conditions.append("best_stability_score >= ?")
            params.append(float(min_stability))

        if query:
            conditions.append("(title LIKE ? OR hypothesis LIKE ? OR notes LIKE ? OR tags LIKE ?)")
            q_pat = f"%{query}%"
            params.extend([q_pat, q_pat, q_pat, q_pat])

        if tag:
            conditions.append("tags LIKE ?")
            params.append(f"%{tag}%")

        where_str = ("WHERE " + " AND ".join(conditions)) if conditions else ""

        valid_sort_cols = {
            'created_at', 'best_profit_factor', 'best_stability_score',
            'best_winrate', 'best_sharpe', 'symbol', 'strategy'
        }
        sort_col = sort_by if sort_by in valid_sort_cols else 'created_at'
        order_dir = 'ASC' if order.upper() == 'ASC' else 'DESC'

        try:
            with self._get_conn() as conn:
                count_row = conn.execute(
                    f"SELECT COUNT(*) FROM research_experiments {where_str}",
                    params
                ).fetchone()
                total = count_row[0] if count_row else 0

                query_str = f"""
                    SELECT * FROM research_experiments
                    {where_str}
                    ORDER BY {sort_col} {order_dir}
                    LIMIT ? OFFSET ?
                """
                exec_params = list(params) + [limit, offset]
                rows = conn.execute(query_str, exec_params).fetchall()
                results = [self._row_to_dict(r) for r in rows]

                return results, total
        except Exception as e:
            logger.error(f"[ResearchStore] Error listando experimentos: {e}")
            return [], 0

    def get_reopen_payload(self, exp_id: str) -> Optional[Dict[str, Any]]:
        """
        Devuelve el objeto de configuración exacto y reproducible para relanzar
        o clonar la investigación.
        """
        exp = self.get_experiment(exp_id)
        if not exp:
            return None

        config_raw = exp.get('config_json') or '{}'
        try:
            config_parsed = json.loads(config_raw) if isinstance(config_raw, str) else config_raw
        except Exception:
            config_parsed = {}

        return {
            "experiment_id": exp.get('experiment_id'),
            "title": exp.get('title'),
            "hypothesis": exp.get('hypothesis'),
            "symbol": exp.get('symbol'),
            "strategy": exp.get('strategy'),
            "timeframe": exp.get('timeframe'),
            "bars_count": exp.get('bars_count'),
            "bot_version": exp.get('bot_version'),
            "git_commit": exp.get('git_commit'),
            "config": config_parsed,
            "tags": exp.get('tags'),
            "notes": exp.get('notes'),
            "reopened_at": datetime.now(timezone.utc).isoformat()
        }

    def delete_experiment(self, exp_id: str) -> bool:
        """Elimina una investigación de la base de datos."""
        try:
            with self._get_conn() as conn:
                cur = conn.execute(
                    "DELETE FROM research_experiments WHERE experiment_id = ?",
                    (exp_id,)
                )
                conn.commit()
                return cur.rowcount > 0
        except Exception as e:
            logger.error(f"[ResearchStore] Error eliminando experimento {exp_id}: {e}")
            return False

    def _row_to_dict(self, row: sqlite3.Row) -> Dict[str, Any]:
        d = dict(row)
        for json_field in ['config_json', 'metrics_json', 'tags', 'environment_meta']:
            if d.get(json_field) and isinstance(d[json_field], str):
                try:
                    d[json_field] = json.loads(d[json_field])
                except Exception:
                    pass
        return d


_research_store_instance: Optional[ResearchStore] = None

def get_research_store(db_path: str = _DEFAULT_DB) -> ResearchStore:
    """Obtiene la instancia singleton de ResearchStore."""
    global _research_store_instance
    if _research_store_instance is None:
        _research_store_instance = ResearchStore(db_path)
    return _research_store_instance
