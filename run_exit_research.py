"""
run_exit_research_runner.py — Runner unificado para el protocolo Exit Research

Único script Python de entrada para TODOS los símbolos.
No hay lógica específica por símbolo aquí. El sistema descubre
automáticamente la estrategia registrada para el símbolo indicado.

Uso:
    python run_exit_research_runner.py --symbol EURUSD --bars 20000
    python run_exit_research_runner.py --symbol XAUUSD --bars 10000
    python run_exit_research_runner.py --symbol BTCEUR --bars 20000

El BAT run_exit_research.bat usa este script como único punto de entrada.
"""

from __future__ import annotations

import argparse
import io
import json
import logging
import os
import sys
from datetime import datetime, timezone
from typing import Dict, Any, Optional

# ── Forzar UTF-8 en stdout/stderr (Windows cp1252 no soporta ≈ × → etc.) ──────
if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
if sys.stderr.encoding and sys.stderr.encoding.lower() != "utf-8":
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

# ── Logging ───────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-7s  %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)


# ── Constantes ────────────────────────────────────────────────────────────────
RULES_CONFIG_PATH = os.path.join(os.path.dirname(__file__), "rules_config.json")
RESULTS_BASE      = os.path.join(os.path.dirname(__file__), "backtest_results", "exit_research")


# ── Lectura de configuración ──────────────────────────────────────────────────

def load_rules_config() -> Dict:
    """Carga rules_config.json. Retorna dict vacío si no existe o falla."""
    try:
        with open(RULES_CONFIG_PATH, encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        logger.warning("rules_config.json no encontrado. Usando configuración de defaults.")
        return {}
    except Exception as e:
        logger.error("Error leyendo rules_config.json: %s", e)
        return {}


def get_symbol_config(symbol: str, cfg: Dict) -> Dict:
    """
    Extrae el bloque de configuración para el símbolo indicado.
    Soporta tanto 'EURUSD' como 'eurusd' como claves.
    """
    key_variants = [symbol.upper(), symbol.lower(), symbol]
    for key in key_variants:
        if key in cfg:
            return cfg[key]
    return {}


def get_sl_tp_from_strategy(strategy_instance) -> tuple[float, float]:
    """
    Extrae sl_atr_multiplier y tp_atr_multiplier del default config de la estrategia.
    Fallback: SL=1.5, TP=3.0 (RR 1:2).
    """
    try:
        cfg = strategy_instance._get_default_config()
        sl = float(cfg.get("sl_atr_multiplier", 1.5))
        tp = float(cfg.get("tp_atr_multiplier", 3.0))
        return sl, tp
    except Exception:
        return 1.5, 3.0


# ── Variante de producción ────────────────────────────────────────────────────

def build_production_variant(sl_mult: float, tp_mult: float):
    """
    Construye la variante 'current_production' que refleja exactamente
    el SL/TP configurado en rules_config.json para ese símbolo.
    Permite comparar todas las variantes de investigación contra
    la salida actual de producción.
    """
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


# ── Runner principal ──────────────────────────────────────────────────────────

def run_exit_research(
    symbol:  str,
    bars:    int,
    verbose: bool = True,
) -> Dict:
    """
    Ejecuta el pipeline completo de Exit Research para cualquier símbolo.

    1. Carga la estrategia registrada en strategy_adapter para el símbolo.
    2. Lee SL/TP de rules_config.json (o defaults de la estrategia).
    3. Construye la variante 'current_production' basada en esos parámetros.
    4. Instancia ExitResearchRunner(symbol=symbol) — pip_size se inyecta automáticamente.
    5. Ejecuta run_all() que internamente hace:
       - Backtest (12 variantes + current_production)
       - Walk-Forward
       - Monte Carlo
       - Stability Score
       - Guardado de sesión

    Returns:
        report_dict con todos los resultados.
    """
    from core.exit_research.runner import ExitResearchRunner
    from core.exit_research.variants import ALL_VARIANTS
    from core.exit_research.strategy_adapter import adapter_for_symbol

    symbol = symbol.upper()

    # ── Cargar estrategia vía registry ────────────────────────────────────────
    logger.info("[Runner] Cargando estrategia para símbolo: %s", symbol)
    try:
        adapter = adapter_for_symbol(symbol)
    except (ValueError, ImportError, AttributeError) as e:
        logger.error("[Runner] No se pudo cargar la estrategia para %s: %s", symbol, e)
        raise

    # ── Leer SL/TP de config ──────────────────────────────────────────────────
    cfg = load_rules_config()
    sym_cfg = get_symbol_config(symbol, cfg)

    # Prioridad: rules_config > defaults de la estrategia
    sl_mult_cfg = sym_cfg.get("sl_atr_multiplier") or sym_cfg.get("sl_multiplier")
    tp_mult_cfg = sym_cfg.get("tp_atr_multiplier") or sym_cfg.get("tp_multiplier")

    sl_default, tp_default = get_sl_tp_from_strategy(adapter.strategy)
    sl_mult = float(sl_mult_cfg) if sl_mult_cfg is not None else sl_default
    tp_mult = float(tp_mult_cfg) if tp_mult_cfg is not None else tp_default

    rr = tp_mult / sl_mult if sl_mult > 0 else 0
    logger.info(
        "[Runner] Config: SL=%.2f×ATR  TP=%.2f×ATR  (RR≈1:%.1f)",
        sl_mult, tp_mult, rr,
    )

    # Actualizar el config del adapter con los valores reales
    adapter.config["sl_atr_multiplier"] = sl_mult
    adapter.config["tp_atr_multiplier"] = tp_mult

    # ── Construir lista de variantes ──────────────────────────────────────────
    prod_variant = build_production_variant(sl_mult, tp_mult)
    all_variants = [prod_variant] + list(ALL_VARIANTS)

    # ── Instanciar runner (pip_size se inyecta automáticamente por símbolo) ───
    runner = ExitResearchRunner(
        symbol   = symbol,
        strategy = adapter,
        variants = all_variants,
    )

    logger.info(
        "[Runner] Iniciando Exit Research: symbol=%s  bars=%d  variantes=%d",
        symbol, bars, len(all_variants),
    )

    report = runner.run_all(bars=bars, save=True, verbose=verbose)
    return report


# ── Análisis interpretativo ───────────────────────────────────────────────────

def generate_analysis(report: Dict, symbol: str, sl_mult: float, tp_mult: float) -> str:
    """
    Genera un resumen markdown del Exit Research.
    Nivel 1: decisión ejecutiva.
    Nivel 2: tabla completa + métricas clave.
    """
    results   = report.get("results", {})
    comp      = report.get("comparison_table", [])
    concl     = report.get("conclusions", {})
    run_id    = report.get("run_id", "unknown")
    generated = report.get("generated_at", "")

    max_level_str = str(max(
        (int(lv) for v in results.values()
         for lv, r in v.items() if r.get("metrics")),
        default=20000,
    ))

    def m(vn: str) -> Dict:
        r = results.get(vn, {}).get(max_level_str, {})
        return (r.get("metrics") or {}) if r else {}

    def fmt(v, d=2):
        if v is None: return "—"
        try: return f"{float(v):.{d}f}"
        except: return "—"

    rr = tp_mult / sl_mult if sl_mult > 0 else 0
    prod_m    = m("current_production")
    prod_stab = float(prod_m.get("stability_score") or 0)
    best_row  = comp[0] if comp else {}
    best_var  = best_row.get("variant", "—")
    best_stab = float(best_row.get("stability_score") or 0)
    impv      = (best_stab - prod_stab) / prod_stab * 100 if prod_stab > 0 else 0

    if best_var == "current_production" or impv < 5:
        verdict = "**MANTENER** salida actual. Sin mejora significativa."
    elif impv < 15:
        verdict = f"**CONSIDERAR** `{best_var}`. Mejora moderada (+{impv:.1f}% Stability)."
    else:
        verdict = f"**RECOMENDADO** `{best_var}`. Mejora relevante (+{impv:.1f}% Stability)."

    lines = [
        f"# Análisis Exit Research — {symbol}",
        "",
        f"**Run ID:** `{run_id}` | **Generado:** {generated}",
        f"**Symbol:** `{symbol}` | **Config producción:** SL={sl_mult}×ATR  TP={tp_mult}×ATR  (RR≈1:{rr:.1f})",
        f"**Dataset:** {max_level_str} velas H1",
        "",
        "---",
        "## Nivel 1 — Decisión Ejecutiva",
        "",
        f"### → {verdict}",
        "",
        "| Criterio | Valor |",
        "|---------|-------|",
        f"| Producción actual | PF={fmt(prod_m.get('profit_factor'))}  WR={fmt(prod_m.get('winrate'),1)}%  Stability={fmt(prod_stab,1)} |",
        f"| Mejor variante    | `{best_var}` — Stability={fmt(best_stab,1)} pts |",
        f"| Recomendada live  | `{concl.get('recommended_for_live','—')}` |",
        f"| Más rentable      | `{concl.get('highest_profit','—')}` |",
        f"| Mejor WF          | `{concl.get('best_walk_forward','—')}` |",
        "",
        "---",
        "## Nivel 2 — Tabla Completa",
        "",
        "| # | Variante | PF | WR% | Pips | MaxDD | Cap% | WF | Stability |",
        "|--:|---------|---:|----:|-----:|------:|-----:|----:|----------:|",
    ]

    for row in comp:
        vn   = row.get("variant", "")
        mi   = m(vn)
        wf   = mi.get("wf_stability") or "—"
        tag  = " ◄" if vn == "current_production" else ""
        lines.append(
            f"| {row.get('rank','')} | `{vn}`{tag} "
            f"| {fmt(row.get('profit_factor'))} "
            f"| {fmt(row.get('winrate'),1)} "
            f"| {fmt(row.get('total_pips'),0)} "
            f"| {fmt(row.get('max_drawdown'),0)} "
            f"| {fmt(mi.get('profit_captured_pct'),1)} "
            f"| {wf} "
            f"| **{fmt(row.get('stability_score'),1)}** |"
        )

    return "\n".join(lines)


def save_analysis(report: Dict, symbol: str, sl_mult: float, tp_mult: float) -> None:
    """Guarda el análisis interpretativo junto a los archivos del runner."""
    run_id      = report.get("run_id", "unknown")
    session_dir = os.path.join(RESULTS_BASE, run_id)
    os.makedirs(session_dir, exist_ok=True)

    content = generate_analysis(report, symbol, sl_mult, tp_mult)
    path    = os.path.join(session_dir, "analysis.md")
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    logger.info("[Runner] Análisis guardado: %s", path)
    print()
    print(content)


# ── CLI ───────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="LastEdge Exit Research — Runner unificado para cualquier símbolo"
    )
    parser.add_argument(
        "--symbol", default="EURUSD",
        help="Símbolo a analizar: EURUSD, XAUUSD, BTCEUR… (default: EURUSD)"
    )
    parser.add_argument(
        "--bars", type=int, default=20_000,
        help="Velas H1 para el backtest (default: 20000)"
    )
    parser.add_argument(
        "--verbose", action="store_true", default=True,
        help="Logging detallado (default: on)"
    )
    parser.add_argument(
        "--no-verbose", dest="verbose", action="store_false",
        help="Reducir logging"
    )
    args = parser.parse_args()

    symbol = args.symbol.upper().strip()
    bars   = args.bars

    if bars < 5000:
        logger.error("--bars debe ser >= 5000 (mínimo recomendado para resultados estadísticos).")
        sys.exit(1)

    # ── Cargar config para mostrar info previa ────────────────────────────────
    cfg       = load_rules_config()
    sym_cfg   = get_symbol_config(symbol, cfg)

    # Obtener SL/TP para el banner (reutilizamos la lógica del runner)
    from core.exit_research.strategy_adapter import adapter_for_symbol, _STRATEGY_REGISTRY
    if symbol not in _STRATEGY_REGISTRY:
        registered = ", ".join(_STRATEGY_REGISTRY.keys())
        logger.error(
            "Símbolo '%s' no registrado. Disponibles: %s", symbol, registered
        )
        sys.exit(1)

    try:
        tmp_adapter = adapter_for_symbol(symbol)
    except Exception as e:
        logger.error("No se pudo cargar la estrategia para %s: %s", symbol, e)
        sys.exit(1)

    sl_default, tp_default = get_sl_tp_from_strategy(tmp_adapter.strategy)
    sl_mult = float(sym_cfg.get("sl_atr_multiplier") or sym_cfg.get("sl_multiplier") or sl_default)
    tp_mult = float(sym_cfg.get("tp_atr_multiplier") or sym_cfg.get("tp_multiplier") or tp_default)
    rr      = tp_mult / sl_mult if sl_mult > 0 else 0

    # ── Banner ────────────────────────────────────────────────────────────────
    print()
    print("=" * 70)
    print("  LastEdge — Exit Research Protocol")
    print("=" * 70)
    print(f"  Símbolo:     {symbol}")
    print(f"  Estrategia:  {tmp_adapter.name}")
    print(f"  Velas:       {bars:,} H1")
    print(f"  Config:      SL={sl_mult}×ATR  TP={tp_mult}×ATR  (RR≈1:{rr:.1f})")
    print(f"  Variantes:   12 estándar + Current Production")
    print(f"  Walk-Fwd:    incluido")
    print(f"  Monte Carlo: incluido")
    print(f"  Inicio:      {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}")
    print("=" * 70)
    print()

    # ── Ejecución ─────────────────────────────────────────────────────────────
    try:
        report = run_exit_research(symbol=symbol, bars=bars, verbose=args.verbose)
    except Exception as e:
        logger.error("[Runner] Ejecución fallida: %s", e, exc_info=True)
        sys.exit(1)

    # ── Guardar y mostrar análisis ────────────────────────────────────────────
    save_analysis(report, symbol, sl_mult, tp_mult)

    # ── Resumen final ─────────────────────────────────────────────────────────
    comp    = report.get("comparison_table", [])
    best    = comp[0] if comp else {}
    run_id  = report.get("run_id", "unknown")
    rec     = report.get("conclusions", {}).get("recommended_for_live", "—")

    print()
    print("=" * 70)
    print("  PROTOCOLO COMPLETADO")
    print("=" * 70)
    print(f"  Símbolo:                {symbol}")
    print(f"  Mejor variante:         {best.get('variant','—')}")
    print(f"  Stability Score:        {best.get('stability_score','—')}")
    print(f"  Recomendada para live:  {rec}")
    print(f"  Run ID:                 {run_id}")
    print(f"  Resultados en:          backtest_results/exit_research/{run_id}/")
    print("=" * 70)
    print()


if __name__ == "__main__":
    main()
