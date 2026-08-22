"""
Monte Carlo Simulation — core/montecarlo.py

Ejecuta N simulaciones sobre el historial de trades del backtest para estimar:
  - Distribución de profit factors posibles
  - Distribución de drawdown máximo
  - Probabilidad de ruina (equity < umbral de ruina)
  - Percentiles de rendimiento (p5, p25, p50, p75, p95)

La simulación reordena aleatoriamente la secuencia de trades (bootstrap
sin reposición por defecto, con reposición opcional) para modelar la
variabilidad que produce el azar en el orden de entradas/salidas.

Uso básico:
    from core.montecarlo import MonteCarlo
    from core.replay_engine import ReplaySignal

    mc = MonteCarlo(n_simulations=5000)
    report = mc.run(signals)           # lista de ReplaySignal
    print(report.summary())

Uso desde Discord (/backtest):
    mc_report = MonteCarlo().run(engine.get_signals())
    await channel.send(mc_report.to_discord_embed())
"""

from __future__ import annotations

import logging
import random
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Tuple
import json
import os
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

# ── Constantes ────────────────────────────────────────────────────────────────
DEFAULT_N_SIMULATIONS  = 5_000   # suficiente para estimar percentiles estables
DEFAULT_RUIN_THRESHOLD = -30.0   # drawdown de −30% de la equity inicial = ruina
DEFAULT_STARTING_PIPS  = 0.0     # equity de partida en pips (puede ser cualquier base)


# ── Estructuras de datos ──────────────────────────────────────────────────────

@dataclass
class TradeRecord:
    """
    Representación mínima de un trade para Monte Carlo.
    Puede construirse desde ReplaySignal o desde un dict de paper/live trading.
    """
    profit_pips: float        # positivo = ganancia, negativo = pérdida
    result: str               # 'WIN' | 'LOSS' | 'PENDING'
    symbol: str = 'UNKNOWN'
    confidence: str = 'MEDIUM'

    @classmethod
    def from_replay_signal(cls, sig) -> 'TradeRecord':
        """Crea TradeRecord desde un ReplaySignal."""
        return cls(
            profit_pips=float(sig.profit_pips or 0.0),
            result=sig.result or 'PENDING',
            symbol=sig.symbol,
            confidence=sig.confidence,
        )

    @classmethod
    def from_dict(cls, d: dict) -> 'TradeRecord':
        """Crea TradeRecord desde un dict (paper/live journal)."""
        return cls(
            profit_pips=float(d.get('profit_pips', 0.0)),
            result=d.get('result', 'PENDING'),
            symbol=d.get('symbol', 'UNKNOWN'),
            confidence=d.get('confidence', 'MEDIUM'),
        )


@dataclass
class SimulationPath:
    """Resultado de una sola simulación (secuencia de equity en pips)."""
    final_equity:    float
    max_drawdown:    float   # en pips
    max_drawdown_pct: float  # como % del pico anterior
    profit_factor:   float
    winrate:         float   # 0–100
    ruined:          bool    # True si tocó el umbral de ruina


@dataclass
class MonteCarloReport:
    """Reporte completo del análisis Monte Carlo."""
    n_simulations:    int
    n_trades:         int
    symbol:           str
    ruin_threshold:   float

    # Estadísticas de las N trayectorias
    prob_ruin:        float          # probabilidad de ruina (0–1)
    prob_profitable:  float          # probabilidad de equity final > 0 (0–1)

    # Percentiles de equity final
    p5_equity:        float
    p25_equity:       float
    p50_equity:       float
    p75_equity:       float
    p95_equity:       float

    # Percentiles de drawdown máximo
    p50_drawdown:     float
    p75_drawdown:     float
    p95_drawdown:     float

    # De las simulaciones originales (primer run = secuencia real)
    original_equity:  float
    original_dd:      float
    original_pf:      float
    original_winrate: float

    # Promedio del profit factor entre simulaciones
    avg_profit_factor: float

    # Metadatos
    timestamp:        str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    # ── Formateo ─────────────────────────────────────────────────────────────

    def summary(self) -> str:
        """Devuelve texto legible para CLI."""
        ruin_pct = self.prob_ruin * 100
        profit_pct = self.prob_profitable * 100
        lines = [
            f"{'═'*65}",
            f"  MONTE CARLO: {self.symbol}  ({self.n_simulations:,} simulaciones · {self.n_trades} trades)",
            f"{'═'*65}",
            f"  Secuencia REAL:  Equity {self.original_equity:+.1f} pips | "
            f"DD {self.original_dd:.1f} | PF {self.original_pf:.2f} | WR {self.original_winrate:.1f}%",
            f"",
            f"  Probabilidad de beneficio  : {profit_pct:>5.1f}%",
            f"  Probabilidad de ruina      : {ruin_pct:>5.1f}%  "
            f"(umbral: {self.ruin_threshold:+.0f} pips drawdown)",
            f"",
            f"  Equity final (percentiles):",
            f"    p5  = {self.p5_equity:+.1f} pips   (peor escenario probable)",
            f"    p25 = {self.p25_equity:+.1f} pips",
            f"    p50 = {self.p50_equity:+.1f} pips   (mediana)",
            f"    p75 = {self.p75_equity:+.1f} pips",
            f"    p95 = {self.p95_equity:+.1f} pips   (mejor escenario probable)",
            f"",
            f"  Drawdown máximo (percentiles):",
            f"    p50 = {self.p50_drawdown:.1f} pips",
            f"    p75 = {self.p75_drawdown:.1f} pips",
            f"    p95 = {self.p95_drawdown:.1f} pips   (escenario pesimista)",
            f"",
            f"  Profit Factor promedio     : {self.avg_profit_factor:.2f}",
            f"{'═'*65}",
        ]
        return "\n".join(lines)

    def to_discord_embed(self) -> str:
        """Formato compacto para enviar como mensaje Discord (< 2000 chars)."""
        ruin_pct = self.prob_ruin * 100
        profit_pct = self.prob_profitable * 100
        icon = "✅" if self.prob_ruin < 0.05 else ("⚠️" if self.prob_ruin < 0.15 else "❌")
        lines = [
            f"**📊 Monte Carlo — {self.symbol}** ({self.n_simulations:,} sim · {self.n_trades} trades)",
            f"",
            f"**Secuencia real:** equity `{self.original_equity:+.1f}` pip | "
            f"DD `{self.original_dd:.1f}` | PF `{self.original_pf:.2f}` | WR `{self.original_winrate:.1f}%`",
            f"",
            f"**Probabilidades:**",
            f"  {icon} Ruina: **{ruin_pct:.1f}%** | Ganancia: **{profit_pct:.1f}%**",
            f"",
            f"**Equity final (pip):**",
            f"  p5=`{self.p5_equity:+.0f}` · p25=`{self.p25_equity:+.0f}` · "
            f"p50=`{self.p50_equity:+.0f}` · p75=`{self.p75_equity:+.0f}` · p95=`{self.p95_equity:+.0f}`",
            f"",
            f"**Max Drawdown (pip):**",
            f"  p50=`{self.p50_drawdown:.0f}` · p75=`{self.p75_drawdown:.0f}` · p95=`{self.p95_drawdown:.0f}`",
            f"",
            f"**PF promedio:** `{self.avg_profit_factor:.2f}`",
        ]
        return "\n".join(lines)

    def to_dict(self) -> Dict:
        """Serializa a dict para guardar en JSON."""
        return {
            'n_simulations':    self.n_simulations,
            'n_trades':         self.n_trades,
            'symbol':           self.symbol,
            'ruin_threshold':   self.ruin_threshold,
            'prob_ruin':        round(self.prob_ruin, 4),
            'prob_profitable':  round(self.prob_profitable, 4),
            'p5_equity':        round(self.p5_equity, 2),
            'p25_equity':       round(self.p25_equity, 2),
            'p50_equity':       round(self.p50_equity, 2),
            'p75_equity':       round(self.p75_equity, 2),
            'p95_equity':       round(self.p95_equity, 2),
            'p50_drawdown':     round(self.p50_drawdown, 2),
            'p75_drawdown':     round(self.p75_drawdown, 2),
            'p95_drawdown':     round(self.p95_drawdown, 2),
            'original_equity':  round(self.original_equity, 2),
            'original_dd':      round(self.original_dd, 2),
            'original_pf':      round(self.original_pf, 2),
            'original_winrate': round(self.original_winrate, 2),
            'avg_profit_factor':round(self.avg_profit_factor, 3),
            'timestamp':        self.timestamp,
        }


# ── Motor de simulación ───────────────────────────────────────────────────────

class MonteCarlo:
    """
    Simulador Monte Carlo para secuencias de trades de backtest.

    Parámetros:
        n_simulations:   Número de permutaciones a generar (default 5000).
        with_replacement: Si True, muestrea con reposición (bootstrap clásico).
                          Si False (default), reordena sin reposición (permutación).
                          Sin reposición es más conservador y realista para n_trades pequeño.
        ruin_threshold:  Drawdown en pips desde el pico que define 'ruina'
                         (negativo, default −30).
        seed:            Semilla para reproducibilidad (None = aleatorio).
    """

    def __init__(
        self,
        n_simulations:    int   = DEFAULT_N_SIMULATIONS,
        with_replacement: bool  = False,
        ruin_threshold:   float = DEFAULT_RUIN_THRESHOLD,
        seed:             Optional[int] = None,
    ):
        self.n_simulations    = n_simulations
        self.with_replacement = with_replacement
        # Enforce ruin threshold is negative pips relative to start
        self.ruin_threshold   = -abs(ruin_threshold)
        self._rng = random.Random(seed)

    # ── API pública ───────────────────────────────────────────────────────────

    def run(
        self,
        signals,             # List[ReplaySignal] | List[TradeRecord] | List[dict]
        symbol: str = 'UNKNOWN',
    ) -> MonteCarloReport:
        """
        Ejecuta las N simulaciones sobre la secuencia de trades.

        Args:
            signals: Lista de ReplaySignal, TradeRecord o dict con campo 'profit_pips'.
            symbol:  Nombre del instrumento (solo para etiquetado del reporte).

        Returns:
            MonteCarloReport con todas las métricas calculadas.
        """
        trades = self._normalize_signals(signals)

        # Solo trades cerrados (WIN o LOSS)
        closed = [t for t in trades if t.result in ('WIN', 'LOSS')]

        if len(closed) < 2:
            logger.warning(
                f"[MC] Menos de 2 trades cerrados ({len(closed)}); "
                "resultados no significativos."
            )

        # Equity real (secuencia original)
        original_path = self._simulate_path(closed, shuffle=False)

        if not closed:
            # Sin trades, devolvemos reporte vacío
            return self._empty_report(symbol)

        # N permutaciones
        paths: List[SimulationPath] = [original_path]
        for _ in range(self.n_simulations - 1):
            paths.append(self._simulate_path(closed, shuffle=True))

        return self._build_report(paths, original_path, closed, symbol)

    def save(self, report: MonteCarloReport, output_dir: str = None) -> str:
        """
        Guarda el reporte en JSON dentro de backtest_results/monte_carlo/.

        Returns:
            Ruta al archivo guardado.
        """
        if output_dir is None:
            base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            output_dir = os.path.join(base, 'backtest_results', 'monte_carlo')

        os.makedirs(output_dir, exist_ok=True)

        ts = datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')
        filename = f"montecarlo_{report.symbol}_{ts}.json"
        path = os.path.join(output_dir, filename)

        with open(path, 'w', encoding='utf-8') as f:
            json.dump(report.to_dict(), f, indent=2, ensure_ascii=False)

        logger.info(f"[MC] Reporte guardado: {path}")
        return path

    # ── Lógica interna ────────────────────────────────────────────────────────

    def _normalize_signals(self, signals) -> List[TradeRecord]:
        """Convierte cualquier formato de entrada a List[TradeRecord]."""
        result = []
        for s in signals:
            if isinstance(s, TradeRecord):
                result.append(s)
            elif isinstance(s, dict):
                result.append(TradeRecord.from_dict(s))
            else:
                # Asumir ReplaySignal (duck-typing)
                try:
                    result.append(TradeRecord.from_replay_signal(s))
                except Exception as e:
                    logger.debug(f"[MC] No se pudo convertir trade: {e}")
        return result

    def _simulate_path(self, closed_trades: List[TradeRecord], shuffle: bool) -> SimulationPath:
        """Genera una trayectoria de equity para una permutación de trades."""
        if not closed_trades:
            return SimulationPath(
                final_equity=0.0, max_drawdown=0.0, max_drawdown_pct=0.0,
                profit_factor=0.0, winrate=0.0, ruined=False,
            )

        if shuffle:
            if self.with_replacement:
                sequence = [self._rng.choice(closed_trades) for _ in closed_trades]
            else:
                sequence = closed_trades[:]
                self._rng.shuffle(sequence)
        else:
            sequence = closed_trades

        equity = DEFAULT_STARTING_PIPS
        peak   = equity
        max_dd = 0.0
        max_dd_pct = 0.0
        wins   = 0
        total_wins_pips  = 0.0
        total_loss_pips  = 0.0
        ruined = False
        processed_count = 0

        for trade in sequence:
            if ruined:
                break

            processed_count += 1
            equity += trade.profit_pips

            if equity > peak:
                peak = equity

            current_dd = peak - equity   # siempre ≥ 0
            if current_dd > max_dd:
                max_dd = current_dd

            dd_pct = (current_dd / abs(peak)) * 100 if peak != 0 else 0.0
            if dd_pct > max_dd_pct:
                max_dd_pct = dd_pct

            # Verificar ruina: si la equity acumulada cae por debajo del umbral negativo de ruina
            if equity <= self.ruin_threshold:
                ruined = True

            # Acumuladores de PF/WR
            if trade.profit_pips > 0:
                wins += 1
                total_wins_pips += trade.profit_pips
            else:
                total_loss_pips += abs(trade.profit_pips)

        pf = total_wins_pips / total_loss_pips if total_loss_pips > 0 else (
            float('inf') if total_wins_pips > 0 else 0.0
        )
        wr = (wins / processed_count) * 100 if processed_count > 0 else 0.0

        return SimulationPath(
            final_equity=equity,
            max_drawdown=max_dd,
            max_drawdown_pct=max_dd_pct,
            profit_factor=pf,
            winrate=wr,
            ruined=ruined,
        )

    def _build_report(
        self,
        paths: List[SimulationPath],
        original: SimulationPath,
        closed_trades: List[TradeRecord],
        symbol: str,
    ) -> MonteCarloReport:
        """Agrega las N trayectorias en un MonteCarloReport."""
        final_equities = sorted(p.final_equity for p in paths)
        drawdowns      = sorted(p.max_drawdown  for p in paths)
        pfs            = [p.profit_factor for p in paths if p.profit_factor != float('inf')]

        n = len(paths)

        def percentile(sorted_list: list, pct: float) -> float:
            if not sorted_list:
                return 0.0
            idx = int(pct * (len(sorted_list) - 1))
            return sorted_list[idx]

        prob_ruin       = sum(1 for p in paths if p.ruined) / n
        prob_profitable = sum(1 for p in paths if p.final_equity > 0) / n
        avg_pf          = sum(pfs) / len(pfs) if pfs else 0.0

        # Profit factor de la secuencia original (ya calculado en SimulationPath)
        # Winrate original
        wins_orig = sum(1 for t in closed_trades if t.profit_pips > 0)
        wr_orig   = (wins_orig / len(closed_trades)) * 100 if closed_trades else 0.0

        return MonteCarloReport(
            n_simulations   = n,
            n_trades        = len(closed_trades),
            symbol          = symbol,
            ruin_threshold  = self.ruin_threshold,
            prob_ruin       = round(prob_ruin, 4),
            prob_profitable = round(prob_profitable, 4),
            p5_equity   = percentile(final_equities, 0.05),
            p25_equity  = percentile(final_equities, 0.25),
            p50_equity  = percentile(final_equities, 0.50),
            p75_equity  = percentile(final_equities, 0.75),
            p95_equity  = percentile(final_equities, 0.95),
            p50_drawdown = percentile(drawdowns, 0.50),
            p75_drawdown = percentile(drawdowns, 0.75),
            p95_drawdown = percentile(drawdowns, 0.95),
            original_equity  = original.final_equity,
            original_dd      = original.max_drawdown,
            original_pf      = original.profit_factor if original.profit_factor != float('inf') else 999.0,
            original_winrate = wr_orig,
            avg_profit_factor = avg_pf,
        )

    def _empty_report(self, symbol: str) -> MonteCarloReport:
        """Reporte vacío cuando no hay trades suficientes."""
        return MonteCarloReport(
            n_simulations=0, n_trades=0, symbol=symbol,
            ruin_threshold=self.ruin_threshold,
            prob_ruin=0.0, prob_profitable=0.0,
            p5_equity=0.0, p25_equity=0.0, p50_equity=0.0,
            p75_equity=0.0, p95_equity=0.0,
            p50_drawdown=0.0, p75_drawdown=0.0, p95_drawdown=0.0,
            original_equity=0.0, original_dd=0.0,
            original_pf=0.0, original_winrate=0.0,
            avg_profit_factor=0.0,
        )


# ── Función de conveniencia ───────────────────────────────────────────────────

def run_montecarlo(
    signals,
    symbol:       str   = 'UNKNOWN',
    n_simulations: int  = DEFAULT_N_SIMULATIONS,
    ruin_threshold: float = DEFAULT_RUIN_THRESHOLD,
    save_to_disk:  bool = True,
    seed:          Optional[int] = None,
) -> MonteCarloReport:
    """
    Wrapper de conveniencia: crea MonteCarlo, ejecuta y guarda opcionalmenteel reporte.

    Args:
        signals:        Lista de ReplaySignal, TradeRecord o dict.
        symbol:         Nombre del par (para etiquetado).
        n_simulations:  Número de simulaciones.
        ruin_threshold: Drawdown en pips que define ruina (negativo).
        save_to_disk:   Si True, guarda JSON en backtest_results/monte_carlo/.
        seed:           Semilla para reproducibilidad.

    Returns:
        MonteCarloReport
    """
    mc = MonteCarlo(
        n_simulations=n_simulations,
        ruin_threshold=ruin_threshold,
        seed=seed,
    )
    report = mc.run(signals, symbol=symbol)

    if save_to_disk and report.n_trades > 0:
        try:
            mc.save(report)
        except Exception as e:
            logger.warning(f"[MC] Error guardando reporte: {e}")

    return report
