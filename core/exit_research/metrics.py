"""
Exit Research — Métricas extendidas + Stability Score.

Calcula las ~20 métricas solicitadas sobre una lista de ReplaySignal-like
objetos y genera un Stability Score compuesto.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field, asdict
from typing import List, Optional, Dict, Any
import logging

logger = logging.getLogger(__name__)


@dataclass
class ExtendedMetrics:
    """Todas las métricas para una variante de salida."""

    variant_name:  str
    variant_label: str
    n_bars:        int  # velas de backtest

    # ── Básicas ───────────────────────────────────────────────────────────────
    signals:       int   = 0
    wins:          int   = 0
    losses:        int   = 0
    pending:       int   = 0
    winrate:       float = 0.0   # %

    # ── P&L ───────────────────────────────────────────────────────────────────
    total_pips:    float = 0.0
    avg_win:       float = 0.0   # pips
    avg_loss:      float = 0.0   # pips (valor absoluto)
    profit_factor: float = 0.0
    expectancy:    float = 0.0   # pips por trade

    # ── Drawdown ──────────────────────────────────────────────────────────────
    max_drawdown:  float = 0.0   # pips (peak-to-trough)
    max_dd_pct:    float = 0.0   # % respecto al pico

    # ── Rachas ────────────────────────────────────────────────────────────────
    longest_win_streak:  int = 0
    longest_loss_streak: int = 0

    # ── Duración ──────────────────────────────────────────────────────────────
    avg_duration_bars:   float = 0.0   # velas H1

    # ── MAE / MFE ─────────────────────────────────────────────────────────────
    # Maximum Adverse Excursion y Maximum Favorable Excursion (en pips)
    mae_mean:            float = 0.0   # MAE medio (todos los trades cerrados)
    mfe_mean:            float = 0.0   # MFE medio (todos los trades cerrados)
    mae_winners:         float = 0.0   # MAE medio solo en trades ganadores
    mae_losers:          float = 0.0   # MAE medio solo en trades perdedores
    mfe_winners:         float = 0.0   # MFE medio solo en trades ganadores
    mfe_losers:          float = 0.0   # MFE medio solo en trades perdedores
    profit_captured_pct: float = 0.0   # avg_win / mfe_winners × 100

    # ── Ratios de riesgo ─────────────────────────────────────────────────────
    recovery_factor: float = 0.0   # total_pips / max_drawdown
    sharpe:          float = 0.0   # simplificado (media/std trades)
    sortino:         float = 0.0   # solo desviación de pérdidas
    calmar:          float = 0.0   # total_pips / max_drawdown (≈ Calmar anual)
    ulcer_index:     float = 0.0   # raíz del mean(drawdown²)
    recovery_time:   float = 0.0   # velas medias para recuperar cada DD

    # ── Proyecciones ─────────────────────────────────────────────────────────
    # Aproximadas asumiendo H1 y ~250 días hábiles/año (≈5000 velas)
    profit_per_year:  float = 0.0
    profit_per_month: float = 0.0
    dd_annual_est:    float = 0.0

    # ── Stability Score ───────────────────────────────────────────────────────
    stability_score:   float = 0.0   # 0–100

    # ── Scoring Analysis & Stratification ────────────────────────────────────
    avg_score_all:       float = 0.0
    avg_score_winners:   float = 0.0
    avg_score_losers:    float = 0.0
    score_edge_delta:    float = 0.0
    scoring_buckets:     List[Dict[str, Any]] = field(default_factory=list)

    # ── Datos crudos para walk-forward / MC ──────────────────────────────────
    # Se rellenan externamente por el runner
    wf_stability:     Optional[str] = None   # STABLE / MARGINAL / UNSTABLE
    mc_prob_ruin:     Optional[float] = None
    mc_prob_profit:   Optional[float] = None
    monthly_pf_std:   Optional[float] = None  # desviación del PF mensual (consistencia)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def compute_metrics(
    variant_name:  str,
    variant_label: str,
    n_bars:        int,
    trades: List,   # lista de objetos con .result, .profit_pips, .bar_index, .exit_bar
) -> ExtendedMetrics:
    """
    Calcula todas las métricas a partir de una lista de trades cerrados.

    Args:
        trades: lista de objetos ReplaySignal (o similar) con atributos:
                result ('WIN'|'LOSS'|'PENDING'), profit_pips, bar_index, exit_bar
    """
    m = ExtendedMetrics(
        variant_name=variant_name,
        variant_label=variant_label,
        n_bars=n_bars,
    )

    closed = [t for t in trades if t.result in ("WIN", "LOSS")]
    m.signals  = len(trades)
    m.wins     = sum(1 for t in closed if t.result == "WIN")
    m.losses   = sum(1 for t in closed if t.result == "LOSS")
    m.pending  = sum(1 for t in trades if t.result == "PENDING")

    if not closed:
        return m

    n = len(closed)
    m.winrate = m.wins / n * 100

    pips = [t.profit_pips or 0.0 for t in closed]
    m.total_pips = sum(pips)

    win_pips  = [p for p in pips if p > 0]
    loss_pips = [abs(p) for p in pips if p < 0]

    m.avg_win  = sum(win_pips)  / len(win_pips)  if win_pips  else 0.0
    m.avg_loss = sum(loss_pips) / len(loss_pips) if loss_pips else 0.0

    gross_win  = sum(win_pips)
    gross_loss = sum(loss_pips)
    m.profit_factor = gross_win / gross_loss if gross_loss > 0 else (float("inf") if gross_win > 0 else 0.0)

    m.expectancy = m.total_pips / n

    # ── Drawdown ──────────────────────────────────────────────────────────────
    equity = 0.0
    peak   = 0.0
    dd_samples = []
    recovery_times = []
    dd_start_peak  = 0.0
    in_dd          = False
    dd_bars        = 0

    for t in closed:
        equity += t.profit_pips or 0.0
        if equity > peak:
            if in_dd:
                recovery_times.append(dd_bars)
            peak   = equity
            in_dd  = False
            dd_bars = 0
        else:
            if not in_dd and equity < peak:
                in_dd = True
                dd_start_peak = peak
                dd_bars = 0
            if in_dd:
                dd_bars += 1

        current_dd = peak - equity
        dd_samples.append(current_dd)
        if current_dd > m.max_drawdown:
            m.max_drawdown = current_dd

    m.max_dd_pct = (m.max_drawdown / peak * 100) if peak > 0 else 0.0
    m.recovery_time = sum(recovery_times) / len(recovery_times) if recovery_times else 0.0

    # Ulcer Index
    if dd_samples:
        m.ulcer_index = math.sqrt(sum(d**2 for d in dd_samples) / len(dd_samples))

    # ── Rachas ────────────────────────────────────────────────────────────────
    max_win_streak = max_loss_streak = cur_win = cur_loss = 0
    for t in closed:
        if t.result == "WIN":
            cur_win += 1; cur_loss = 0
            max_win_streak = max(max_win_streak, cur_win)
        else:
            cur_loss += 1; cur_win = 0
            max_loss_streak = max(max_loss_streak, cur_loss)
    m.longest_win_streak  = max_win_streak
    m.longest_loss_streak = max_loss_streak

    # ── Duración ──────────────────────────────────────────────────────────────
    durations = []
    for t in closed:
        if t.exit_bar is not None and t.bar_index is not None:
            durations.append(t.exit_bar - t.bar_index)
    m.avg_duration_bars = sum(durations) / len(durations) if durations else 0.0

    # ── MAE / MFE ─────────────────────────────────────────────────────────────
    # Los campos mae_pips / mfe_pips se añadieron a _Trade en runner.py.
    # Si el objeto trade no tiene esos atributos (compatibilidad con código
    # antiguo que usa ReplaySignal) los tratamos como 0.
    def _get_mae(t) -> float:
        return float(getattr(t, "mae_pips", 0.0) or 0.0)

    def _get_mfe(t) -> float:
        return float(getattr(t, "mfe_pips", 0.0) or 0.0)

    all_mae = [_get_mae(t) for t in closed]
    all_mfe = [_get_mfe(t) for t in closed]

    m.mae_mean = sum(all_mae) / len(all_mae) if all_mae else 0.0
    m.mfe_mean = sum(all_mfe) / len(all_mfe) if all_mfe else 0.0

    winners = [t for t in closed if t.result == "WIN"]
    losers  = [t for t in closed if t.result == "LOSS"]

    mae_w = [_get_mae(t) for t in winners]
    mfe_w = [_get_mfe(t) for t in winners]
    mae_l = [_get_mae(t) for t in losers]
    mfe_l = [_get_mfe(t) for t in losers]

    m.mae_winners = sum(mae_w) / len(mae_w) if mae_w else 0.0
    m.mfe_winners = sum(mfe_w) / len(mfe_w) if mfe_w else 0.0
    m.mae_losers  = sum(mae_l) / len(mae_l) if mae_l else 0.0
    m.mfe_losers  = sum(mfe_l) / len(mfe_l) if mfe_l else 0.0

    # Profit Captured % = cuánto del movimiento favorable capturó la salida.
    # Se calcula sobre trades ganadores donde MFE > 0.
    # Si avg_win > mfe_winners (por ej. en algunos casos de parcial) se limita a 100 %.
    if m.mfe_winners > 0 and m.avg_win > 0:
        m.profit_captured_pct = min(100.0, round(m.avg_win / m.mfe_winners * 100, 2))
    else:
        m.profit_captured_pct = 0.0

    # ── Ratios ────────────────────────────────────────────────────────────────
    m.recovery_factor = m.total_pips / m.max_drawdown if m.max_drawdown > 0 else float("inf")
    m.calmar          = m.total_pips / m.max_drawdown if m.max_drawdown > 0 else float("inf")

    mean_p  = m.total_pips / n
    std_p   = math.sqrt(sum((p - mean_p)**2 for p in pips) / n) if n > 1 else 0.0
    m.sharpe = mean_p / std_p if std_p > 0 else 0.0

    # Sortino: solo downside deviación
    neg_pips  = [p for p in pips if p < 0]
    if neg_pips:
        downside_std = math.sqrt(sum(p**2 for p in neg_pips) / n)
        m.sortino = mean_p / downside_std if downside_std > 0 else 0.0
    else:
        m.sortino = float("inf")

    # ── Proyecciones (H1: 5000 velas ≈ 1 año) ────────────────────────────────
    if n_bars > 0:
        scale_year  = 5000 / n_bars
        scale_month = scale_year / 12
        m.profit_per_year  = m.total_pips  * scale_year
        m.profit_per_month = m.total_pips  * scale_month
        m.dd_annual_est    = m.max_drawdown * scale_year

    # ── Stability Score ───────────────────────────────────────────────────────
    m.stability_score = _stability_score(m)

    # ── Scoring Analysis & Stratification ────────────────────────────────────
    trade_scores = [getattr(t, "score", None) for t in closed if getattr(t, "score", None) is not None]
    if trade_scores:
        scores_all = [float(s) for s in trade_scores]
        scores_win = [float(t.score) for t in closed if t.result == "WIN" and getattr(t, "score", None) is not None]
        scores_loss = [float(t.score) for t in closed if t.result == "LOSS" and getattr(t, "score", None) is not None]

        m.avg_score_all = round(sum(scores_all) / len(scores_all), 4) if scores_all else 0.0
        m.avg_score_winners = round(sum(scores_win) / len(scores_win), 4) if scores_win else 0.0
        m.avg_score_losers = round(sum(scores_loss) / len(scores_loss), 4) if scores_loss else 0.0
        m.score_edge_delta = round(m.avg_score_winners - m.avg_score_losers, 4)

        bucket_defs = [
            {"tier": "ELITE", "label": "0.90 – 1.00 (Elite)", "min_score": 0.90, "max_score": 1.01},
            {"tier": "VERY_HIGH", "label": "0.80 – 0.89 (Very High)", "min_score": 0.80, "max_score": 0.90},
            {"tier": "HIGH", "label": "0.70 – 0.79 (High)", "min_score": 0.70, "max_score": 0.80},
            {"tier": "MEDIUM", "label": "0.60 – 0.69 (Medium)", "min_score": 0.60, "max_score": 0.70},
            {"tier": "LOW", "label": "< 0.60 (Low / Filtered)", "min_score": 0.00, "max_score": 0.60},
        ]

        buckets = []
        for b_def in bucket_defs:
            b_trades = [
                t for t in closed
                if getattr(t, "score", None) is not None
                and b_def["min_score"] <= float(t.score) < b_def["max_score"]
            ]
            b_count = len(b_trades)
            if b_count > 0:
                b_wins = sum(1 for t in b_trades if t.result == "WIN")
                b_losses = sum(1 for t in b_trades if t.result == "LOSS")
                b_wr = round((b_wins / b_count * 100.0), 1)
                b_pips = [t.profit_pips or 0.0 for t in b_trades]
                b_net_pips = round(sum(b_pips), 2)
                b_gross_win = sum(p for p in b_pips if p > 0)
                b_gross_loss = abs(sum(p for p in b_pips if p < 0))
                b_pf = round(b_gross_win / b_gross_loss, 2) if b_gross_loss > 0 else (99.0 if b_gross_win > 0 else 0.0)
            else:
                b_wins = 0
                b_losses = 0
                b_wr = 0.0
                b_pf = 0.0
                b_net_pips = 0.0

            buckets.append({
                "tier": b_def["tier"],
                "range_label": b_def["label"],
                "min_score": b_def["min_score"],
                "max_score": b_def["max_score"],
                "trades_count": b_count,
                "trades_pct": round((b_count / len(closed) * 100.0), 1) if closed else 0.0,
                "wins": b_wins,
                "losses": b_losses,
                "win_rate_pct": b_wr,
                "profit_factor": b_pf,
                "net_pips": b_net_pips,
            })

        m.scoring_buckets = buckets

    return m


def _stability_score(m: ExtendedMetrics) -> float:
    """
    Puntuación compuesta 0–100 basada en estabilidad, no solo en PF.

    Componentes:
      30% — Profit Factor (normalizado, techo 3.0)
      20% — Winrate (normalizado vs 50% mínimo)
      20% — Recovery Factor (techo 5.0)
      15% — Sharpe (techo 2.0)
      10% — Longest losing streak (penalización)
       5% — Calmar (techo 3.0)
    """
    def clamp(v, lo, hi): return max(lo, min(hi, v))

    pf_score  = clamp((m.profit_factor - 1.0) / 2.0, 0, 1)          # PF 1→3 = 0→1
    wr_score  = clamp((m.winrate - 30.0) / 40.0, 0, 1)              # WR 30→70% = 0→1
    rf_score  = clamp(m.recovery_factor / 5.0, 0, 1)                # RF 0→5 = 0→1
    sh_score  = clamp(m.sharpe / 2.0, 0, 1)                         # Sharpe 0→2 = 0→1
    ls_score  = clamp(1 - (m.longest_loss_streak - 2) / 8.0, 0, 1)  # streak 2→10 → penaliza
    ca_score  = clamp(m.calmar / 3.0, 0, 1) if m.calmar != float("inf") else 1.0

    raw = (
        pf_score  * 0.30 +
        wr_score  * 0.20 +
        rf_score  * 0.20 +
        sh_score  * 0.15 +
        ls_score  * 0.10 +
        ca_score  * 0.05
    )

    # Penalizar si hay datos de WF/MC cargados externamente
    # mc_prob_ruin es proporción [0,1]; convertir a % y restar 5 puntos de umbral
    # Req 5.4: penalty = 0.5 × max(0, mc_prob_ruin × 100 − 5) puntos
    mc_penalty = 0.0
    if m.mc_prob_ruin is not None:
        mc_penalty = 0.5 * max(0.0, m.mc_prob_ruin * 100 - 5)

    return round(max(0.0, raw * 100 - mc_penalty), 2)


def monthly_consistency(
    trades: List,
    n_bars: int,
    hours_per_bar: int = 1,
) -> Dict[str, float]:
    """
    Agrupa los trades por mes aproximado y devuelve estadísticas de consistencia.
    Asume que bar_index es índice en un array de H1 que empieza en 0.
    """
    from collections import defaultdict
    # Estimar mes: 720 velas H1 ≈ 1 mes
    BARS_PER_MONTH = 720

    monthly: Dict[int, List[float]] = defaultdict(list)
    for t in trades:
        if t.result not in ("WIN", "LOSS"):
            continue
        month_idx = t.bar_index // BARS_PER_MONTH
        monthly[month_idx].append(t.profit_pips or 0.0)

    if not monthly:
        return {"n_months": 0, "profitable_months_pct": 0.0, "pf_std": 0.0}

    profitable = 0
    pfs = []
    for month_pips in monthly.values():
        total = sum(month_pips)
        if total > 0:
            profitable += 1
        wins  = sum(p for p in month_pips if p > 0)
        losses = abs(sum(p for p in month_pips if p < 0))
        pfs.append(wins / losses if losses > 0 else (2.0 if wins > 0 else 1.0))

    n = len(monthly)
    pf_mean = sum(pfs) / n
    pf_std  = math.sqrt(sum((p - pf_mean)**2 for p in pfs) / n) if n > 1 else 0.0

    return {
        "n_months": n,
        "profitable_months_pct": profitable / n * 100,
        "pf_std": round(pf_std, 3),
    }
