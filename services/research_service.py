"""
LastEdge Strategy Lab — Quantitative Research Service
services/research_service.py

Orchestrates multi-phase quantitative research for trading strategies:
  1. Historical Dataset Ingestion (Local Parquet Cache / MT5 Terminal)
  2. Multi-Window Walk Forward Analysis (WFA) to detect overfitting & degradation
  3. Monte Carlo Permutation Stress Testing (5,000 iterations for ruin probability)
  4. Composite Robustness & Stability Score Calculation
  5. Audit Persistence in SQLite Research Database (research.db)
"""

from __future__ import annotations

import json
import logging
import math
import os
from datetime import datetime, timezone
from typing import Dict, Any, Optional, List

import numpy as np
import pandas as pd

from services.research_store import get_research_store, ResearchStore
from services.backtest_service import get_backtest_service

logger = logging.getLogger(__name__)


class ResearchService:
    """Provides high-performance quantitative research & WFA simulations."""

    def __init__(self, research_store: Optional[ResearchStore] = None):
        self.research_store = research_store or get_research_store()
        self.backtest_service = get_backtest_service()

    def run_research(
        self,
        symbol: str = "EURUSD",
        strategy_name: Optional[str] = None,
        timeframe: str = "H1",
        bars: int = 10000,
        n_simulations: int = 2000,
    ) -> Dict[str, Any]:
        """
        Executes an end-to-end scientific research simulation:
          - Multi-window Walk Forward Analysis (WFA)
          - Monte Carlo permutation simulation
          - Overfitting & stability rating
          - Persistence in research.db
        """
        t0 = datetime.now(timezone.utc)
        sym = symbol.upper().strip()
        tf = timeframe.upper().strip()

        # 1. Resolve strategy & metadata from catalog
        from core.strategy_catalog import get_strategy_metadata, get_strategies_for_symbol
        available = get_strategies_for_symbol(sym)
        if not available:
            return {"ok": False, "error": f"Símbolo no soportado: {sym}"}

        selected_meta = None
        if strategy_name:
            strat_req = strategy_name.lower().strip()
            for s in available:
                if s["id"].lower() == strat_req:
                    selected_meta = s
                    break
            if not selected_meta:
                return {
                    "ok": False,
                    "error": f"Estrategia '{strategy_name}' no válida para {sym}. Permitidas: {[s['id'] for s in available]}",
                }
        else:
            selected_meta = available[0]

        strat_id = selected_meta["id"]
        allowed_tfs = [t.upper() for t in selected_meta.get("allowed_timeframes", ["H1"])]
        if tf not in allowed_tfs:
            tf = selected_meta.get("default_timeframe", allowed_tfs[0]).upper()

        lookback_req = int(selected_meta.get("lookback_min", 200))

        # 2. Ensure historical dataset
        df_candles = self.backtest_service._ensure_dataset(sym, timeframe=tf, requested_bars=bars)
        total_bars = len(df_candles)

        # 3. Multi-window Walk-Forward Analysis (WFA)
        # Adapt window sizes dynamically to available bars
        available_bars = max(200, total_bars - lookback_req)
        train_bars = max(200, int(available_bars * 0.50))
        test_bars = max(100, int(available_bars * 0.25))
        step_bars = max(100, int(available_bars * 0.25))

        from core.walkforward import WalkForwardTester
        wf_tester = WalkForwardTester(
            train_bars=train_bars,
            test_bars=test_bars,
            step_bars=step_bars,
            lookback=lookback_req,
        )

        wf_report = wf_tester.run(
            symbol=sym,
            strategy=strat_id,
            total_bars=available_bars,
            timeframe=tf,
            df_override=df_candles,
        )

        # 4. Monte Carlo Simulation on Baseline Replay
        from core.replay_engine import ReplayEngine
        replay = ReplayEngine(lookback_window=lookback_req)
        stats = replay.run_replay(
            symbol=sym,
            bars=available_bars,
            strategy=strat_id,
            timeframe=tf,
            df_override=df_candles,
        )

        signals = replay.signals
        trades = [s for s in signals if s.result in ("WIN", "LOSS")]
        pnl_series = [t.profit_pips or 0.0 for t in trades]

        from core.trade_costs import PIP_VALUE_PER_LOT_USD, DEFAULT_LOT_SIZE
        lot = DEFAULT_LOT_SIZE.get(sym, 0.10)
        pip_val_lot = PIP_VALUE_PER_LOT_USD.get(sym, 10.0)
        pip_value_usd = lot * pip_val_lot

        ruin_count = 0
        profitable_count = 0
        drawdowns_money = []
        n_sims = min(max(500, n_simulations), 5000)

        if len(pnl_series) >= 10:
            for _ in range(n_sims):
                sim_trades = np.random.choice(pnl_series, size=len(pnl_series), replace=True)
                sim_eq = 10000.0
                sim_peak = 10000.0
                sim_max_dd = 0.0
                sim_ruined = False

                for p in sim_trades:
                    sim_eq += p * pip_value_usd
                    if sim_eq > sim_peak:
                        sim_peak = sim_eq
                    dd = sim_peak - sim_eq
                    if dd > sim_max_dd:
                        sim_max_dd = dd
                    if (sim_peak - sim_eq) / sim_peak >= 0.20:
                        sim_ruined = True

                if not sim_ruined:
                    pass
                else:
                    ruin_count += 1

                if sim_eq > 10000.0:
                    profitable_count += 1

                drawdowns_money.append(sim_max_dd)

            prob_profitable_pct = round((profitable_count / n_sims) * 100.0, 1)
            ruin_prob_pct = round((ruin_count / n_sims) * 100.0, 1)
            p95_dd_money = round(float(np.percentile(drawdowns_money, 95)), 2)
            p95_dd_pct = round((p95_dd_money / 10000.0) * 100.0, 2)
        else:
            prob_profitable_pct = 50.0 if stats.total_pips > 0 else 0.0
            ruin_prob_pct = 0.0
            p95_dd_money = 0.0
            p95_dd_pct = 0.0

        # 5. Composite Stability Score (0.0 to 100.0)
        consistency_norm = min(1.0, max(0.0, wf_report.consistency_score)) * 35.0
        ruin_component = max(0.0, 25.0 - (ruin_prob_pct * 1.5))
        pf_component = min(25.0, max(0.0, (wf_report.avg_test_pf / 2.0) * 25.0))
        dd_component = max(0.0, 15.0 - (p95_dd_pct * 0.75))

        stability_score = round(consistency_norm + ruin_component + pf_component + dd_component, 1)
        stability_rating = wf_report.stability_rating or "UNKNOWN"

        # 6. Scientific Decision & Verdict
        if stability_score >= 60.0 and stability_rating in ("STABLE", "MARGINAL") and ruin_prob_pct <= 5.0:
            decision_status = "PROMOTED"
            verdict_badge = "PROMETEDORA (ALTA ESTABILIDAD)"
            verdict_color = "#10B981"
            verdict_icon = "fa-circle-check"
            verdict_title = "ESTRATEGIA ROBUSTA FUERA DE MUESTRA"
            verdict_summary = (
                f"El modelo superó la validación científica Walk-Forward (Consistency Score: {wf_report.consistency_score:.2f}, "
                f"Estabilidad: {stability_rating}) y resistencia Monte Carlo ({prob_profitable_pct}% rentabilidad, "
                f"{ruin_prob_pct}% riesgo de ruina). Apta para promoción controlada."
            )
        elif stability_score >= 35.0 and ruin_prob_pct <= 15.0:
            decision_status = "CANDIDATE"
            verdict_badge = "CANDIDATA EN OBSERVACIÓN"
            verdict_color = "#F59E0B"
            verdict_icon = "fa-triangle-exclamation"
            verdict_title = "ESTABILIDAD MODERADA — REQUIERE OPTIMIZACIÓN"
            verdict_summary = (
                f"La estrategia demuestra consistencia aceptable ({wf_report.consistency_score:.2f} / 1.00), "
                f"pero presenta degradación en ventanas TEST (PF Train {wf_report.avg_train_pf:.2f} vs Test {wf_report.avg_test_pf:.2f}). "
                f"Mantener como candidata y evaluar variantes de Take Profit / Trailing Stop."
            )
        else:
            decision_status = "REJECTED"
            verdict_badge = "RECHAZADA (SOBRE-AJUSTADA / ALTO RIESGO)"
            verdict_color = "#EF4444"
            verdict_icon = "fa-ban"
            verdict_title = "ESTRATEGIA DESCARTADA POR INESTABILIDAD"
            verdict_summary = (
                f"ALERTA: El modelo sufre sobre-ajuste severo (Overfitting) o riesgo de ruina crítico "
                f"({ruin_prob_pct}% > 15%). La rentabilidad observada en backtest simple no se sostiene "
                f"en periodos no vistos fuera de muestra."
            )

        duration_ms = round((datetime.now(timezone.utc) - t0).total_seconds() * 1000, 1)

        # 7. Persistence into research.db
        exp_id = f"exp_{sym.lower()}_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}"
        notes_str = (
            f"WFA: {len(wf_report.windows)} wds (Score {wf_report.consistency_score:.2f}) | "
            f"Stability: {stability_score} | MC Ruin: {ruin_prob_pct}% | "
            f"Test PF: {wf_report.avg_test_pf:.2f}"
        )

        wfa_windows_data = [
            {
                "window": w.window_index,
                "train_pf": round(w.train_pf, 2),
                "test_pf": round(w.test_pf, 2),
                "pf_degradation": round(w.pf_degradation, 2),
                "train_winrate": round(w.train_winrate, 1),
                "test_winrate": round(w.test_winrate, 1),
                "consistency": round(w.consistency_score, 2),
            }
            for w in wf_report.windows
        ]

        metrics_payload = {
            "stability_score": stability_score,
            "stability_rating": stability_rating,
            "consistency_score": round(wf_report.consistency_score, 2),
            "avg_train_pf": round(wf_report.avg_train_pf, 2),
            "avg_test_pf": round(wf_report.avg_test_pf, 2),
            "avg_pf_degradation": round(wf_report.avg_pf_degradation, 2),
            "avg_winrate_train": round(wf_report.avg_winrate_train, 1),
            "avg_winrate_test": round(wf_report.avg_winrate_test, 1),
            "monte_carlo_prob_profitable_pct": prob_profitable_pct,
            "monte_carlo_ruin_pct": ruin_prob_pct,
            "monte_carlo_p95_dd_money": p95_dd_money,
            "monte_carlo_p95_dd_pct": p95_dd_pct,
            "windows": wfa_windows_data,
        }

        try:
            self.research_store.create_experiment({
                "experiment_id": exp_id,
                "title": f"Research {sym} {tf} — WFA & Monte Carlo ({strat_id})",
                "hypothesis": f"Validación de robustez científica Walk Forward & Monte Carlo para {sym} {strat_id} sobre {total_bars} barras.",
                "symbol": sym,
                "strategy": strat_id,
                "timeframe": tf,
                "bars_count": total_bars,
                "status": "COMPLETED",
                "decision_status": decision_status,
                "decision_notes": verdict_summary,
                "best_variant": f"WFA ({stability_rating})",
                "best_profit_factor": wf_report.avg_test_pf,
                "best_winrate": wf_report.avg_winrate_test,
                "best_stability_score": stability_score,
                "best_max_drawdown": p95_dd_pct,
                "best_mc_ruin_pct": ruin_prob_pct,
                "wf_stability": wf_report.consistency_score,
                "tags": json.dumps(["research", "wfa", sym.lower(), tf.lower()]),
                "notes": notes_str,
                "metrics_json": json.dumps(metrics_payload, ensure_ascii=False),
            })
        except Exception as e:
            logger.debug(f"[ResearchService] Error storing experiment: {e}")

        return {
            "ok": True,
            "experiment_id": exp_id,
            "symbol": sym,
            "strategy": strat_id,
            "timeframe": tf,
            "bars_analyzed": total_bars,
            "duration_ms": duration_ms,
            "stability_score": stability_score,
            "stability_rating": stability_rating,
            "consistency_score": round(wf_report.consistency_score, 2),
            "decision_status": decision_status,
            "wfa": {
                "rating": stability_rating,
                "consistency_score": round(wf_report.consistency_score, 2),
                "mean_train_pf": round(wf_report.avg_train_pf, 2),
                "mean_test_pf": round(wf_report.avg_test_pf, 2),
                "pf_degradation": round(wf_report.avg_pf_degradation, 2),
                "mean_train_wr": round(wf_report.avg_winrate_train, 1),
                "mean_test_wr": round(wf_report.avg_winrate_test, 1),
                "windows_count": len(wfa_windows_data),
                "windows": [
                    {
                        "window_id": w["window"],
                        "train_pf": w["train_pf"],
                        "test_pf": w["test_pf"],
                        "pf_degradation": w["pf_degradation"],
                        "train_wr": w["train_winrate"],
                        "test_wr": w["test_winrate"],
                        "consistency": w["consistency"] >= 0.5,
                    }
                    for w in wfa_windows_data
                ],
            },
            "monte_carlo": {
                "n_simulations": n_sims,
                "ruin_probability_pct": ruin_prob_pct,
                "probability_profitable_pct": prob_profitable_pct,
                "p95_max_drawdown_pct": p95_dd_pct,
                "p95_max_drawdown_usd": p95_dd_money,
            },
            "metrics": metrics_payload,
            "verdict": {
                "tier": "TIER_1_PROMOTED" if decision_status == "PROMOTED" else ("TIER_2_CANDIDATE" if decision_status == "CANDIDATE" else "TIER_3_REJECTED"),
                "badge": verdict_badge,
                "color": verdict_color,
                "icon": verdict_icon,
                "title": verdict_title,
                "summary": verdict_summary,
                "status_tag": decision_status,
                "status": decision_status,
            },
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }


_research_service_instance: Optional[ResearchService] = None


def get_research_service() -> ResearchService:
    global _research_service_instance
    if _research_service_instance is None:
        _research_service_instance = ResearchService()
    return _research_service_instance


__all__ = ["ResearchService", "get_research_service"]
