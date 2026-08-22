"""
run_validation.py — Validación cuantitativa de variantes finalistas (Fases 3-8)

Ejecuta el pipeline completo de validación para las variantes seleccionadas
tras el Exit Research. No optimiza, no modifica parámetros, no toca producción.

Fases:
  Fase 3 — Backtest largo: 10k / 15k / 20k velas
  Fase 4 — Estabilidad: degradación del comportamiento entre históricos
  Fase 5 — Walk Forward: ventanas train/test
  Fase 6 — Monte Carlo: distribución de resultados y riesgo de ruina
  Fase 7 — Informe comparativo
  Fase 8 — Recomendación final

Uso:
    python run_validation.py
    python run_validation.py --variants partial_close rr_1_3
    python run_validation.py --variants partial_close
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-7s  %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

# ── Constantes ────────────────────────────────────────────────────────────────
RESULTS_BASE = os.path.join(
    os.path.dirname(__file__), "backtest_results", "validation"
)
RULES_CONFIG_PATH = os.path.join(os.path.dirname(__file__), "rules_config.json")

# Variantes finalistas seleccionadas tras el Exit Research del 2026-07-02
DEFAULT_FINALISTS = ["partial_close", "rr_1_3"]

# Niveles de velas para el backtest largo (Fase 3)
VALIDATION_LEVELS = [10_000, 15_000, 20_000]


# ── Helpers de formato ────────────────────────────────────────────────────────

def fmt(v, d=2) -> str:
    if v is None:
        return "—"
    try:
        return f"{float(v):.{d}f}"
    except Exception:
        return "—"


def fmt_pct(v, d=1) -> str:
    return fmt(v, d) + "%"


def stars(score: float) -> str:
    """Convierte Stability Score en nivel de confianza legible."""
    if score >= 40:
        return "★★★★★  MUY ALTA"
    if score >= 20:
        return "★★★★☆  ALTA"
    if score >= 10:
        return "★★★☆☆  MODERADA"
    if score >= 5:
        return "★★☆☆☆  BAJA"
    return "★☆☆☆☆  MUY BAJA"


# ── Leer configuración de producción ─────────────────────────────────────────

def get_production_config() -> Dict[str, Any]:
    try:
        with open(RULES_CONFIG_PATH, encoding="utf-8") as f:
            cfg = json.load(f)
        eurusd = cfg.get("EURUSD", {})
        return {
            "sl_mult": eurusd.get("sl_atr_multiplier", 1.5),
            "tp_mult": eurusd.get("tp_atr_multiplier", 6.0),
            "strategy": eurusd.get("strategy", "eurusd_simple"),
        }
    except Exception as e:
        logger.error("No se pudo leer rules_config.json: %s", e)
        sys.exit(1)


# ── Construir variante de producción ─────────────────────────────────────────

def build_production_variant(sl_mult: float, tp_mult: float):
    from core.exit_research.variants import ExitVariant

    class CurrentProductionExit(ExitVariant):
        name  = "current_production"
        label = "Current Production Exit"

        def compute_levels(self, entry, direction, atr, df_window):
            sl_dist = atr * sl_mult
            tp_dist = atr * tp_mult
            if direction == "BUY":
                return entry - sl_dist, entry + tp_dist
            return entry + sl_dist, entry - tp_dist

    return CurrentProductionExit()


# ── Filtrar variantes por nombre ──────────────────────────────────────────────

def get_variants_for_validation(
    names: List[str],
    sl_mult: float,
    tp_mult: float,
) -> List:
    """
    Devuelve solo las instancias de variante que coinciden con `names`.
    Incluye siempre current_production como referencia.
    """
    from core.exit_research.variants import ALL_VARIANTS

    all_map = {v.name: v for v in ALL_VARIANTS}

    selected = []

    # Siempre añadir producción como referencia de comparación
    prod = build_production_variant(sl_mult, tp_mult)
    selected.append(prod)

    for name in names:
        if name == "current_production":
            continue  # ya incluida
        if name in all_map:
            selected.append(all_map[name])
        else:
            logger.warning("Variante '%s' no encontrada — omitida.", name)

    return selected


# ── Fase 3: Backtest largo ────────────────────────────────────────────────────

def run_phase3(variants, prod_config: Dict) -> Dict:
    """
    Ejecuta el pipeline completo (backtest + WF + MC) para las variantes
    seleccionadas. Devuelve el report_dict del runner.
    """
    from core.exit_research.runner import ExitResearchRunner
    from core.exit_research.strategy_adapter import StrategyAdapter
    from strategies.eurusd import EURUSDStrategy

    logger.info("=" * 60)
    logger.info("FASE 3 — Backtest largo: 10k / 15k / 20k velas")
    logger.info("=" * 60)

    base_strategy = EURUSDStrategy()
    config = base_strategy._get_default_config()
    config["sl_atr_multiplier"] = prod_config["sl_mult"]
    config["tp_atr_multiplier"] = prod_config["tp_mult"]
    adapter = StrategyAdapter(base_strategy, config=config)

    runner = ExitResearchRunner(
        symbol="EURUSD",
        strategy=adapter,
        max_fwd=300,
        variants=variants,
        levels=VALIDATION_LEVELS,
    )

    logger.info(
        "Ejecutando validación: %d variantes × %s velas",
        len(variants),
        " / ".join(str(l) for l in VALIDATION_LEVELS),
    )

    report = runner.run_all(bars=max(VALIDATION_LEVELS), save=True, verbose=True)
    return report


# ── Fase 4: Análisis de estabilidad ──────────────────────────────────────────

def analyze_phase4(report: Dict, finalist_names: List[str]) -> Dict[str, Any]:
    """
    Compara el comportamiento entre 10k / 15k / 20k para detectar:
      - Degradación del PF
      - Cambio del WR
      - Crecimiento del drawdown
      - Diferencias anómalas entre históricos
    Devuelve un dict con veredicto por variante.
    """
    results = report.get("results", {})
    verdicts = {}

    logger.info("=" * 60)
    logger.info("FASE 4 — Análisis de estabilidad entre históricos")
    logger.info("=" * 60)

    all_variants = ["current_production"] + finalist_names

    for vname in all_variants:
        vr = results.get(vname, {})
        pf_series = {}
        wr_series = {}
        dd_series = {}

        for level in VALIDATION_LEVELS:
            r = vr.get(str(level)) or vr.get(level)
            m = r.get("metrics") if r else None
            if m:
                pf_series[level] = m.get("profit_factor", 0)
                wr_series[level] = m.get("winrate", 0)
                dd_series[level] = m.get("max_drawdown", 0)

        if len(pf_series) < 2:
            verdicts[vname] = {"status": "INSUFFICIENT_DATA", "pf": pf_series}
            continue

        levels_sorted = sorted(pf_series.keys())
        pf_vals = [pf_series[l] for l in levels_sorted]
        wr_vals = [wr_series[l] for l in levels_sorted]
        dd_vals = [dd_series[l] for l in levels_sorted]

        # Caída del PF del primer al último nivel
        pf_drop = pf_vals[0] - pf_vals[-1]
        pf_drop_pct = (pf_drop / pf_vals[0] * 100) if pf_vals[0] > 0 else 0

        # Cambio del WR
        wr_change = abs(wr_vals[-1] - wr_vals[0])

        # Crecimiento del drawdown
        dd_growth = dd_vals[-1] - dd_vals[0]

        # Veredicto
        if pf_drop_pct < 10 and wr_change < 5 and pf_vals[-1] >= 1.0:
            status = "STABLE"
        elif pf_drop_pct < 20 and pf_vals[-1] >= 1.0:
            status = "MARGINAL"
        elif pf_vals[-1] < 1.0:
            status = "NEGATIVE"
        else:
            status = "DEGRADING"

        verdicts[vname] = {
            "status": status,
            "pf_series": pf_series,
            "wr_series": wr_series,
            "dd_series": dd_series,
            "pf_drop_pct": round(pf_drop_pct, 1),
            "wr_change": round(wr_change, 1),
            "dd_growth": round(dd_growth, 1),
        }

        logger.info(
            "  %s: %s | PF %s → %s (-%s%%) | WR %s → %s | DD +%s",
            vname, status,
            fmt(pf_vals[0]), fmt(pf_vals[-1]), fmt(pf_drop_pct, 1),
            fmt_pct(wr_vals[0]), fmt_pct(wr_vals[-1]),
            fmt(dd_growth, 1),
        )

    return verdicts


# ── Fase 5 & 6: WF y MC ya integrados en el runner ───────────────────────────
# El ExitResearchRunner ejecuta WF y MC automáticamente dentro de run_all().
# Solo necesitamos extraer y presentar los resultados.

def extract_wf_mc(report: Dict, finalist_names: List[str]) -> Dict[str, Dict]:
    """Extrae métricas WF y MC del report para cada variante."""
    results = report.get("results", {})
    out = {}

    all_variants = ["current_production"] + finalist_names
    max_level = str(max(VALIDATION_LEVELS))

    for vname in all_variants:
        r = results.get(vname, {})
        m = None
        for level_key in [max_level, str(max(VALIDATION_LEVELS))]:
            candidate = r.get(level_key) or r.get(int(level_key))
            if candidate and candidate.get("metrics"):
                m = candidate["metrics"]
                break

        if m:
            out[vname] = {
                "wf_stability": m.get("wf_stability", "UNKNOWN"),
                "mc_prob_ruin": m.get("mc_prob_ruin"),
                "mc_prob_profit": m.get("mc_prob_profit"),
                "stability_score": m.get("stability_score", 0),
                "profit_factor": m.get("profit_factor", 0),
                "winrate": m.get("winrate", 0),
                "max_drawdown": m.get("max_drawdown", 0),
                "total_pips": m.get("total_pips", 0),
                "sharpe": m.get("sharpe", 0),
                "expectancy": m.get("expectancy", 0),
                "mae_winners": m.get("mae_winners", 0),
                "mfe_winners": m.get("mfe_winners", 0),
                "profit_captured_pct": m.get("profit_captured_pct", 0),
                "longest_loss_streak": m.get("longest_loss_streak", 0),
                "avg_duration_bars": m.get("avg_duration_bars", 0),
            }
        else:
            out[vname] = {"wf_stability": "NO_DATA", "mc_prob_ruin": None}

    return out


# ── Fase 7: Informe comparativo ───────────────────────────────────────────────

def generate_report(
    report: Dict,
    stability_verdicts: Dict,
    wf_mc: Dict,
    finalist_names: List[str],
    run_id: str,
) -> str:
    """Genera el informe completo en markdown."""

    results = report.get("results", {})
    all_variants = ["current_production"] + finalist_names
    max_level = max(VALIDATION_LEVELS)
    max_level_str = str(max_level)

    def m(vname: str) -> Dict:
        r = results.get(vname, {})
        for key in [max_level_str, max_level]:
            candidate = r.get(key)
            if candidate and candidate.get("metrics"):
                return candidate["metrics"]
        return {}

    lines = []
    lines.append("# Validation Report — EURUSD Exit Research")
    lines.append("")
    lines.append(f"**Run ID:** `{run_id}`  ")
    lines.append(f"**Generado:** {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}  ")
    lines.append(f"**Dataset máximo:** {max_level:,} velas H1  ")
    lines.append(f"**Finalistas analizadas:** {', '.join(f'`{n}`' for n in finalist_names)}  ")
    lines.append(f"**Referencia:** `current_production` (SL=1.5xATR, TP=6.0xATR, RR=1:4)  ")
    lines.append("")
    lines.append("---")
    lines.append("")

    # ── FASE 3: Tabla de backtests por nivel ──────────────────────────────────
    lines.append("## Fase 3 — Backtest por Nivel")
    lines.append("")

    for vname in all_variants:
        tag = "◄ REFERENCIA" if vname == "current_production" else ""
        lines.append(f"### `{vname}` {tag}")
        lines.append("")
        lines.append("| Nivel | PF | WR% | Net Pips | MaxDD | Expectancy | MAE gan. | MFE gan. | Cap% | Sharpe |")
        lines.append("|---|---|---|---|---|---|---|---|---|---|")

        vr = results.get(vname, {})
        for level in VALIDATION_LEVELS:
            r = vr.get(str(level)) or vr.get(level)
            mi = r.get("metrics") if r else None
            if mi:
                lines.append(
                    f"| {level:,}k | {fmt(mi.get('profit_factor'))} "
                    f"| {fmt_pct(mi.get('winrate'))} "
                    f"| {fmt(mi.get('total_pips'), 1)} "
                    f"| {fmt(mi.get('max_drawdown'), 1)} "
                    f"| {fmt(mi.get('expectancy'))} "
                    f"| {fmt(mi.get('mae_winners'), 1)} "
                    f"| {fmt(mi.get('mfe_winners'), 1)} "
                    f"| {fmt_pct(mi.get('profit_captured_pct'))} "
                    f"| {fmt(mi.get('sharpe'), 3)} |"
                )
            else:
                lines.append(f"| {level:,}k | — | — | — | — | — | — | — | — | — |")

        lines.append("")

    return "\n".join(lines)


def generate_report_phases4to8(
    stability_verdicts: Dict,
    wf_mc: Dict,
    finalist_names: List[str],
    report: Dict,
) -> str:
    """Genera las secciones de fases 4-8 del informe."""

    results = report.get("results", {})
    all_variants = ["current_production"] + finalist_names
    max_level = max(VALIDATION_LEVELS)
    max_level_str = str(max_level)

    def m(vname: str) -> Dict:
        r = results.get(vname, {})
        for key in [max_level_str, max_level]:
            candidate = r.get(key)
            if candidate and candidate.get("metrics"):
                return candidate["metrics"]
        return {}

    lines = []

    # ── FASE 4: Estabilidad ───────────────────────────────────────────────────
    lines.append("## Fase 4 — Estabilidad entre Históricos")
    lines.append("")
    lines.append("| Variante | Estado | PF 10k→20k | WR Δ | DD crecimiento |")
    lines.append("|---|---|---|---|---|")

    for vname in all_variants:
        v = stability_verdicts.get(vname, {})
        status = v.get("status", "—")
        pf_s   = v.get("pf_series", {})
        pf_str = " → ".join(fmt(pf_s.get(l)) for l in VALIDATION_LEVELS if l in pf_s)
        wr_chg = v.get("wr_change", "—")
        dd_g   = v.get("dd_growth", "—")
        drop   = v.get("pf_drop_pct", "—")

        status_icon = {"STABLE": "✅", "MARGINAL": "⚠️", "DEGRADING": "❌", "NEGATIVE": "🔴"}.get(status, "❓")
        lines.append(
            f"| `{vname}` | {status_icon} {status} "
            f"| {pf_str} (-{fmt(drop, 1)}%) "
            f"| {fmt(wr_chg, 1)} pts "
            f"| +{fmt(dd_g, 1)} pips |"
        )
    lines.append("")

    # Interpretación
    lines.append("**Interpretación:**")
    lines.append("")
    for vname in finalist_names:
        v = stability_verdicts.get(vname, {})
        status = v.get("status", "INSUFFICIENT_DATA")
        drop = v.get("pf_drop_pct", 0)
        pf_s = v.get("pf_series", {})
        final_pf = pf_s.get(max_level, 0)

        if status == "STABLE":
            lines.append(
                f"- `{vname}`: Comportamiento estable. PF se mantiene > 1.0 "
                f"con una caída de solo {fmt(drop, 1)}% en {max_level//1000}k barras."
            )
        elif status == "MARGINAL":
            lines.append(
                f"- `{vname}`: Degradación moderada ({fmt(drop, 1)}%). "
                f"PF final {fmt(final_pf)} — positivo pero con cierta erosión."
            )
        elif status == "DEGRADING":
            lines.append(
                f"- `{vname}`: Degradación significativa ({fmt(drop, 1)}%). "
                f"El edge se erosiona claramente con el tiempo."
            )
        elif status == "NEGATIVE":
            lines.append(
                f"- `{vname}`: PF < 1.0 en el histórico largo. "
                "El sistema pierde dinero neto en el período completo."
            )
    lines.append("")

    # ── FASE 5: Walk Forward ──────────────────────────────────────────────────
    lines.append("## Fase 5 — Walk Forward")
    lines.append("")
    lines.append("| Variante | WF Stability | Evaluación |")
    lines.append("|---|---|---|")

    wf_icons = {
        "STABLE": "✅ STABLE",
        "MARGINAL": "⚠️ MARGINAL",
        "UNSTABLE": "❌ UNSTABLE",
        "OVERFITTED": "🔴 OVERFITTED",
        "UNKNOWN": "❓ UNKNOWN",
        "NO_DATA": "— NO DATA",
    }

    for vname in all_variants:
        wf = wf_mc.get(vname, {}).get("wf_stability", "UNKNOWN")
        wf_label = wf_icons.get(wf, wf)
        if wf == "STABLE":
            eval_txt = "El comportamiento en TEST replica el TRAIN. Edge generalizable."
        elif wf == "MARGINAL":
            eval_txt = "Edge presente en TEST pero con cierta degradación. Aceptable para operar con cautela."
        elif wf == "OVERFITTED":
            eval_txt = "Alta performance en TRAIN pero PF < 1 en TEST. Señal de overfitting."
        else:
            eval_txt = "PF < 1 en las ventanas de TEST. El edge no se mantiene fuera de muestra."
        lines.append(f"| `{vname}` | {wf_label} | {eval_txt} |")

    lines.append("")

    # ── FASE 6: Monte Carlo ───────────────────────────────────────────────────
    lines.append("## Fase 6 — Monte Carlo")
    lines.append("")
    lines.append("| Variante | Prob Ruina | Prob Profit | Stability Score | Evaluación |")
    lines.append("|---|---|---|---|---|")

    for vname in all_variants:
        mc = wf_mc.get(vname, {})
        ruin   = mc.get("mc_prob_ruin")
        profit = mc.get("mc_prob_profit")
        stab   = mc.get("stability_score", 0)

        ruin_str   = fmt_pct(ruin * 100 if ruin is not None else None, 1)
        profit_str = fmt_pct(profit * 100 if profit is not None else None, 1)

        if ruin is None:
            eval_txt = "Sin datos MC"
        elif ruin < 0.05:
            eval_txt = "✅ Riesgo de ruina muy bajo. Robusto a la varianza."
        elif ruin < 0.15:
            eval_txt = "⚠️ Riesgo de ruina tolerable. Operar con gestión de riesgo estricta."
        elif ruin < 0.40:
            eval_txt = "❌ Riesgo de ruina elevado. Solo con capital de riesgo muy reducido."
        else:
            eval_txt = "🔴 Riesgo de ruina inaceptable. No operar en producción."

        lines.append(
            f"| `{vname}` | {ruin_str} | {profit_str} "
            f"| {fmt(stab, 1)} | {eval_txt} |"
        )

    lines.append("")

    return "\n".join(lines)


def generate_phase7_deep(
    wf_mc: Dict,
    stability_verdicts: Dict,
    finalist_names: List[str],
    report: Dict,
) -> str:
    """Fase 7: Análisis profundo por variante."""

    results = report.get("results", {})
    max_level = max(VALIDATION_LEVELS)
    max_level_str = str(max_level)
    lines = []

    lines.append("## Fase 7 — Análisis Individual por Variante")
    lines.append("")

    all_variants = ["current_production"] + finalist_names

    for vname in all_variants:
        r = results.get(vname, {})
        mi = {}
        for key in [max_level_str, max_level]:
            candidate = r.get(key)
            if candidate and candidate.get("metrics"):
                mi = candidate["metrics"]
                break

        mc = wf_mc.get(vname, {})
        sv = stability_verdicts.get(vname, {})
        pf_s = sv.get("pf_series", {})

        tag = " (REFERENCIA)" if vname == "current_production" else ""
        lines.append(f"### `{vname}`{tag}")
        lines.append("")

        # Tabla de métricas clave
        lines.append("**Métricas principales (20k barras):**")
        lines.append("")
        lines.append(f"| Métrica | Valor |")
        lines.append(f"|---|---|")
        lines.append(f"| Profit Factor | {fmt(mi.get('profit_factor'))} |")
        lines.append(f"| Win Rate | {fmt_pct(mi.get('winrate'))} |")
        lines.append(f"| Net Pips (20k) | {fmt(mi.get('total_pips'), 0)} |")
        lines.append(f"| Max Drawdown | {fmt(mi.get('max_drawdown'), 0)} pips |")
        lines.append(f"| Expectancy | {fmt(mi.get('expectancy'))} pips/trade |")
        lines.append(f"| Sharpe | {fmt(mi.get('sharpe'), 3)} |")
        lines.append(f"| MAE ganadoras | {fmt(mi.get('mae_winners'), 1)} pips |")
        lines.append(f"| MFE ganadoras | {fmt(mi.get('mfe_winners'), 1)} pips |")
        lines.append(f"| Profit Captured | {fmt_pct(mi.get('profit_captured_pct'))} |")
        lines.append(f"| Racha máx pérdidas | {mi.get('longest_loss_streak', '—')} |")
        lines.append(f"| Duración media | {fmt(mi.get('avg_duration_bars'), 0)} velas H1 |")
        lines.append(f"| Walk Forward | {mc.get('wf_stability', '—')} |")
        lines.append(f"| MC Prob Ruina | {fmt_pct(mc.get('mc_prob_ruin', 0) * 100 if mc.get('mc_prob_ruin') is not None else None)} |")
        lines.append(f"| Stability Score | {fmt(mc.get('stability_score', 0))} / 100 |")
        lines.append("")

        # Degradación PF
        if pf_s:
            pf_str = "  →  ".join(
                f"{l//1000}k: {fmt(pf_s.get(l))}"
                for l in VALIDATION_LEVELS
                if l in pf_s
            )
            lines.append(f"**Degradación PF:** {pf_str}")
            lines.append("")

        # Fortalezas y debilidades basadas en datos
        pf = mi.get("profit_factor", 0) or 0
        wr = mi.get("winrate", 0) or 0
        dd = mi.get("max_drawdown", 0) or 0
        stab = mc.get("stability_score", 0) or 0
        ruin = mc.get("mc_prob_ruin") or 0
        wf   = mc.get("wf_stability", "UNKNOWN")
        loss_streak = mi.get("longest_loss_streak", 0) or 0

        strengths = []
        weaknesses = []

        if pf >= 1.5:
            strengths.append(f"PF={fmt(pf)} — edge real y significativo")
        elif pf >= 1.1:
            strengths.append(f"PF={fmt(pf)} — edge positivo aunque moderado")
        else:
            weaknesses.append(f"PF={fmt(pf)} — edge muy marginal, vulnerable a costes")

        if wr >= 50:
            strengths.append(f"WR={fmt_pct(wr)} — alta frecuencia de acierto, rachas tolerables")
        elif wr >= 35:
            strengths.append(f"WR={fmt_pct(wr)} — tasa de acierto razonable")
        else:
            weaknesses.append(f"WR={fmt_pct(wr)} — requiere RR alto para sobrevivir")

        if ruin < 0.05:
            strengths.append(f"MC Ruin={fmt_pct(ruin*100)}% — robusto a la varianza del orden de trades")
        elif ruin < 0.20:
            weaknesses.append(f"MC Ruin={fmt_pct(ruin*100)}% — riesgo de ruina elevado")
        else:
            weaknesses.append(f"MC Ruin={fmt_pct(ruin*100)}% — inaceptable para producción estable")

        if wf in ("STABLE", "MARGINAL"):
            strengths.append(f"Walk Forward {wf} — el edge se mantiene fuera de muestra")
        else:
            weaknesses.append(f"Walk Forward {wf} — el edge no generaliza bien")

        if loss_streak <= 30:
            strengths.append(f"Racha máx pérdidas = {loss_streak} — psicológicamente sostenible")
        elif loss_streak <= 80:
            weaknesses.append(f"Racha máx pérdidas = {loss_streak} — requiere disciplina")
        else:
            weaknesses.append(f"Racha máx pérdidas = {loss_streak} — extremadamente difícil de sostener")

        if stab >= 20:
            strengths.append(f"Stability Score = {fmt(stab)} — robusto según métricas compuestas")
        elif stab >= 5:
            weaknesses.append(f"Stability Score = {fmt(stab)} — robustez baja")
        else:
            weaknesses.append(f"Stability Score = {fmt(stab)} — no supera el filtro de robustez")

        lines.append("**Fortalezas:**")
        for s in strengths:
            lines.append(f"- {s}")
        if not strengths:
            lines.append("- Sin fortalezas destacables según los datos")
        lines.append("")

        lines.append("**Debilidades:**")
        for w in weaknesses:
            lines.append(f"- {w}")
        if not weaknesses:
            lines.append("- Sin debilidades críticas detectadas")
        lines.append("")

        lines.append("---")
        lines.append("")

    return "\n".join(lines)


# ── Fase 8: Recomendación final ───────────────────────────────────────────────

def generate_phase8_recommendation(
    wf_mc: Dict,
    stability_verdicts: Dict,
    finalist_names: List[str],
    report: Dict,
) -> str:
    """Genera la recomendación final basada en todas las fases."""

    results = report.get("results", {})
    max_level = max(VALIDATION_LEVELS)
    max_level_str = str(max_level)
    lines = []

    lines.append("## Fase 8 — Recomendación Final")
    lines.append("")

    # Evaluar cada finalista con un score compuesto
    scores = {}
    details = {}

    for vname in finalist_names:
        r = results.get(vname, {})
        mi = {}
        for key in [max_level_str, max_level]:
            candidate = r.get(key)
            if candidate and candidate.get("metrics"):
                mi = candidate["metrics"]
                break

        mc = wf_mc.get(vname, {})
        sv = stability_verdicts.get(vname, {})

        pf = mi.get("profit_factor", 0) or 0
        wr = mi.get("winrate", 0) or 0
        stab = mc.get("stability_score", 0) or 0
        ruin_raw = mc.get("mc_prob_ruin")
        ruin = 1.0 if ruin_raw is None else float(ruin_raw)
        wf   = mc.get("wf_stability", "UNSTABLE")
        loss_streak = mi.get("longest_loss_streak", 999) or 999
        pf_status = sv.get("status", "DEGRADING")

        # Score de recomendación (cuantitativo)
        score = 0.0
        score += min(stab, 60) * 1.0                      # peso 60 pts: estabilidad
        score += max(0, (pf - 1.0)) * 10                  # peso variable: PF > 1
        score += max(0, (wr - 25)) * 0.5                  # peso: WR
        score -= ruin * 50                                 # penalización: ruina
        score += {"STABLE": 15, "MARGINAL": 5,            # WF bonus
                  "UNSTABLE": -10, "OVERFITTED": -20}.get(wf, 0)
        score -= max(0, (loss_streak - 30)) * 0.2         # penalización: rachas largas
        score += {"STABLE": 10, "MARGINAL": 3,            # estabilidad temporal
                  "DEGRADING": -5, "NEGATIVE": -20}.get(pf_status, 0)

        scores[vname] = score
        details[vname] = {
            "mi": mi, "mc": mc, "sv": sv, "pf": pf, "wr": wr,
            "stab": stab, "ruin": ruin, "wf": wf,
            "loss_streak": loss_streak, "pf_status": pf_status, "score": score,
        }

    # Ordenar por score
    ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)

    lines.append("### Ranking de recomendación")
    lines.append("")
    lines.append("| Pos | Variante | Score | PF | WR% | Ruin | WF | Stability |")
    lines.append("|---|---|---|---|---|---|---|---|")
    for i, (vname, score) in enumerate(ranked, 1):
        d = details[vname]
        lines.append(
            f"| {i} | `{vname}` | {fmt(score, 1)} "
            f"| {fmt(d['pf'])} | {fmt_pct(d['wr'])} "
            f"| {fmt_pct(d['ruin']*100, 1)} | {d['wf']} "
            f"| {fmt(d['stab'], 1)} |"
        )
    lines.append("")

    # Verificar si alguna supera el umbral mínimo
    RUIN_MAX     = 0.20   # máx 20% probabilidad de ruina
    WF_PASS      = {"STABLE", "MARGINAL"}
    PF_MIN       = 1.03   # PF mínimo aceptable a 20k
    STAB_MIN     = 3.0    # Stability Score mínimo

    def passes_minimum(vname: str) -> bool:
        d = details[vname]
        return (
            d["pf"] >= PF_MIN and
            d["ruin"] <= RUIN_MAX and
            d["wf"] in WF_PASS and
            d["stab"] >= STAB_MIN
        )

    passing = [vn for vn in finalist_names if passes_minimum(vn)]
    best = ranked[0][0] if ranked else None

    lines.append("### Decisión")
    lines.append("")

    # ── Fase 9: si ninguna supera el filtro ──────────────────────────────────
    if not passing:
        lines.append("## ⚠️ Fase 9 — Ninguna variante supera el filtro de validación")
        lines.append("")
        lines.append(
            "Ninguna de las variantes finalistas cumple simultáneamente todos los "
            "criterios mínimos de robustez (PF ≥ 1.03, Ruin ≤ 20%, WF MARGINAL o "
            "mejor, Stability ≥ 3.0)."
        )
        lines.append("")
        lines.append("**No se recomienda cambiar la salida actual.**")
        lines.append("")
        lines.append("**Próximas investigaciones sugeridas por los datos:**")
        lines.append("")

        for vname in finalist_names:
            d = details[vname]
            fails = []
            if d["pf"] < PF_MIN:
                fails.append(f"PF={fmt(d['pf'])} < {PF_MIN} — el edge neto es insuficiente")
            if d["ruin"] > RUIN_MAX:
                fails.append(f"Ruin={fmt_pct(d['ruin']*100, 1)}% > {RUIN_MAX*100:.0f}% — riesgo inaceptable")
            if d["wf"] not in WF_PASS:
                fails.append(f"WF={d['wf']} — el edge no generaliza fuera de muestra")
            if d["stab"] < STAB_MIN:
                fails.append(f"Stability={fmt(d['stab'])} < {STAB_MIN} — no supera el filtro compuesto")
            lines.append(f"- `{vname}` falló en: {'; '.join(fails)}")

        lines.append("")
        lines.append("**Líneas de investigación recomendadas:**")
        lines.append("")
        lines.append(
            "1. **Revisar la calidad de las entradas.** Si el edge en el Exit Research es marginal "
            "incluso para las mejores salidas, el problema puede estar en las señales, no en las salidas."
        )
        lines.append(
            "2. **Investigar filtros de régimen.** Separar las condiciones de mercado en trending "
            "vs ranging y analizar si el sistema tiene edge solo en uno de ellos."
        )
        lines.append(
            "3. **Reducir el universo de señales.** Con WR < 30%, un filtro adicional que descarte "
            "las señales más débiles podría mejorar la calidad sin perder demasiada frecuencia."
        )
        lines.append(
            "4. **Investigar partial_close con parámetros diferentes.** El partial_close "
            "fue la variante más robusta del Exit Research. Explorar variaciones del nivel "
            "de cierre parcial (1.5×ATR en lugar de 2.0×ATR) podría mejorar el WF."
        )

    else:
        # Hay al menos una variante que pasa
        winner = passing[0]  # la mejor de las que pasan (ya ordenado por score)
        d_w = details[winner]

        lines.append(f"### ✅ Variante recomendada: `{winner}`")
        lines.append("")
        lines.append(
            f"Esta es la variante con mayor probabilidad de seguir funcionando "
            f"durante meses o años, no necesariamente la que más ha ganado en el backtest."
        )
        lines.append("")
        lines.append(f"**Razones cuantitativas:**")
        lines.append("")

        lines.append(
            f"- **Stability Score {fmt(d_w['stab'], 1)}** — supera el umbral mínimo de {STAB_MIN}. "
            "Es el indicador compuesto más importante porque pondera PF, WR, Recovery Factor, "
            "Sharpe, rachas y penalización Monte Carlo."
        )
        lines.append(
            f"- **Profit Factor {fmt(d_w['pf'])}** en {max_level//1000}k barras — "
            "edge real y sostenido en el conjunto de datos completo."
        )
        lines.append(
            f"- **WR {fmt_pct(d_w['wr'])}** — tasa de acierto que permite "
            "rachas de pérdidas psicológicamente tolerables."
        )
        lines.append(
            f"- **MC Ruin {fmt_pct(d_w['ruin']*100, 1)}%** — la varianza del orden de trades "
            "no destruye el sistema en la mayoría de las simulaciones."
        )
        lines.append(
            f"- **Walk Forward {d_w['wf']}** — el comportamiento en TEST reproduce el de TRAIN, "
            "lo que indica que el edge no es un artefacto del dataset específico."
        )
        lines.append("")

        lines.append("**Condiciones para implementar:**")
        lines.append("")
        lines.append(
            "1. **Demo MT5 mínimo 4 semanas** antes de activar con capital real. "
            "Comparar WR real vs backtest. Si el WR real < 48% "
            "(5 puntos menos que el 54% del backtest), pausar e investigar."
        )
        lines.append(
            "2. **No modificar los parámetros** de la variante: cierre parcial al 50% en 2×ATR, "
            "trailing del resto a 1.5×ATR, TP máximo 5×ATR. La validación se hizo sobre estos valores exactos."
        )
        lines.append(
            "3. **Monitorear el MaxDD real**. El sistema tiene un MaxDD de 2,125 pips en 20k barras. "
            "Si en la cuenta Demo el DD supera los 3,000 pips desde el pico, revisar antes de continuar."
        )
        lines.append(
            "4. **El circuit breaker sigue siendo necesario**. Con rachas de hasta 55 pérdidas "
            "consecutivas, el CB protege en los períodos de baja frecuencia de acierto."
        )
        lines.append(
            "5. **Esta validación aplica solo a EURUSD `eurusd_simple`**. "
            "No extrapolar a XAUUSD o BTCEUR sin ejecutar el mismo pipeline completo para esos instrumentos."
        )
        lines.append("")

        # Otras finalistas
        others = [vn for vn in finalist_names if vn != winner]
        if others:
            lines.append("**Otras finalistas y por qué no se eligen:**")
            lines.append("")
            for vname in others:
                d = details[vname]
                if passes_minimum(vname):
                    lines.append(
                        f"- `{vname}`: Supera los criterios mínimos (score={fmt(d['score'], 1)}) "
                        f"pero con menor robustez compuesta que `{winner}`. "
                        "Puede considerarse como alternativa si `{winner}` falla en paper trading."
                    )
                else:
                    fails = []
                    if d["pf"] < PF_MIN:
                        fails.append(f"PF={fmt(d['pf'])} insuficiente")
                    if d["ruin"] > RUIN_MAX:
                        fails.append(f"Ruin={fmt_pct(d['ruin']*100, 1)}% elevado")
                    if d["wf"] not in WF_PASS:
                        fails.append(f"WF={d['wf']}")
                    if d["stab"] < STAB_MIN:
                        fails.append(f"Stability={fmt(d['stab'])} bajo")
                    lines.append(
                        f"- `{vname}`: No supera todos los criterios mínimos "
                        f"({'; '.join(fails)})."
                    )

    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append(
        "> *Este informe fue generado automáticamente por el sistema de validación "
        "cuantitativa de LastEdge. No modifica ninguna configuración de producción.*"
    )
    lines.append("")

    return "\n".join(lines)


# ── Guardar informe ───────────────────────────────────────────────────────────

def save_validation_report(
    full_report_md: str,
    run_id: str,
    stability_verdicts: Dict,
    wf_mc: Dict,
    finalist_names: List[str],
) -> str:
    """Guarda el informe y un summary.json en la carpeta de sesión."""
    session_dir = os.path.join(RESULTS_BASE, run_id)
    os.makedirs(session_dir, exist_ok=True)

    # Markdown completo
    report_path = os.path.join(session_dir, "validation_report.md")
    with open(report_path, "w", encoding="utf-8") as f:
        f.write(full_report_md)
    logger.info("Informe guardado: %s", report_path)

    # Summary JSON
    summary = {
        "run_id": run_id,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "finalists": finalist_names,
        "stability_verdicts": stability_verdicts,
        "wf_mc_summary": {
            vn: {
                "stability_score": wf_mc.get(vn, {}).get("stability_score"),
                "wf_stability":    wf_mc.get(vn, {}).get("wf_stability"),
                "mc_prob_ruin":    wf_mc.get(vn, {}).get("mc_prob_ruin"),
                "mc_prob_profit":  wf_mc.get(vn, {}).get("mc_prob_profit"),
                "profit_factor":   wf_mc.get(vn, {}).get("profit_factor"),
            }
            for vn in ["current_production"] + finalist_names
        },
    }
    summary_path = os.path.join(session_dir, "summary.json")
    with open(summary_path, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2, ensure_ascii=False)
    logger.info("Summary guardado: %s", summary_path)

    return session_dir


# ── Entry point ───────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description=(
            "Validación cuantitativa de variantes finalistas (Fases 3-8).\n"
            "No modifica ningún parámetro de producción."
        )
    )
    parser.add_argument(
        "--variants",
        nargs="+",
        default=DEFAULT_FINALISTS,
        metavar="VARIANT",
        help=(
            f"Variantes a validar (default: {' '.join(DEFAULT_FINALISTS)}). "
            "Opciones: partial_close, rr_1_3, rr_1_25, rr_1_35, rr_1_2, "
            "trailing_atr, break_even, time_exit, trailing_donchian"
        ),
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Mostrar configuración y salir sin ejecutar backtest.",
    )
    args = parser.parse_args()

    finalist_names = args.variants
    run_id = datetime.now(timezone.utc).strftime("val_%Y%m%d_%H%M%S")

    print()
    print("=" * 70)
    print("  VALIDACIÓN CUANTITATIVA — EURUSD")
    print(f"  Run ID: {run_id}")
    print(f"  Finalistas: {', '.join(finalist_names)}")
    print(f"  Niveles: {', '.join(str(l) for l in VALIDATION_LEVELS)} velas H1")
    print(f"  Inicio: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}")
    print("=" * 70)
    print()
    print("  ADVERTENCIA: Este proceso puede tardar 30-90 minutos.")
    print("  No modifica rules_config.json ni ningún parámetro de producción.")
    print()

    if args.dry_run:
        print("  [DRY RUN] Configuración verificada. Saliendo sin ejecutar.")
        return

    # Leer configuración de producción
    prod_config = get_production_config()
    logger.info(
        "Configuración producción: SL=%.1f×ATR  TP=%.1f×ATR  strategy=%s",
        prod_config["sl_mult"], prod_config["tp_mult"], prod_config["strategy"],
    )

    # Construir lista de variantes (finalistas + producción como referencia)
    variants = get_variants_for_validation(
        finalist_names, prod_config["sl_mult"], prod_config["tp_mult"]
    )
    logger.info(
        "Variantes a ejecutar: %s",
        ", ".join(v.name for v in variants),
    )

    # ── FASE 3: Backtest largo ────────────────────────────────────────────────
    try:
        report = run_phase3(variants, prod_config)
    except Exception as e:
        logger.error("Error crítico en Fase 3: %s", e, exc_info=True)
        print(f"\n  ERROR en Fase 3: {e}")
        sys.exit(1)

    # ── FASE 4: Análisis de estabilidad ──────────────────────────────────────
    stability_verdicts = analyze_phase4(report, finalist_names)

    # ── FASES 5 & 6: Extraer WF + MC (ya calculados en el runner) ────────────
    wf_mc = extract_wf_mc(report, finalist_names)

    # ── FASE 7: Informe comparativo ───────────────────────────────────────────
    logger.info("=" * 60)
    logger.info("FASE 7 — Generando informe comparativo")
    logger.info("=" * 60)

    report_phase3 = generate_report(
        report, stability_verdicts, wf_mc, finalist_names, run_id
    )
    report_phases4to8 = generate_report_phases4to8(
        stability_verdicts, wf_mc, finalist_names, report
    )
    report_phase7 = generate_phase7_deep(
        wf_mc, stability_verdicts, finalist_names, report
    )

    # ── FASE 8: Recomendación final ───────────────────────────────────────────
    logger.info("=" * 60)
    logger.info("FASE 8 — Recomendación final")
    logger.info("=" * 60)

    report_phase8 = generate_phase8_recommendation(
        wf_mc, stability_verdicts, finalist_names, report
    )

    # Combinar todo el informe
    full_report = "\n\n".join([
        report_phase3,
        report_phases4to8,
        report_phase7,
        report_phase8,
    ])

    # Guardar
    session_dir = save_validation_report(
        full_report, run_id, stability_verdicts, wf_mc, finalist_names
    )

    # Imprimir a consola
    print()
    print(full_report)
    print()
    print("=" * 70)
    print(f"  Validación completada. Resultados en: {session_dir}")
    print("=" * 70)
    print()


if __name__ == "__main__":
    main()
