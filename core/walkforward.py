"""
Walk-Forward Testing — core/walkforward.py

Divide los datos históricos en ventanas TRAIN/TEST solapadas y ejecuta
el replay engine en cada una. Detecta overfitting midiendo la degradación
entre el período de entrenamiento y el de validación.

Esquema de ventanas (ejemplo con train=6m, test=2m, step=2m):

  |──── TRAIN 6m ────|── TEST 2m ──|
              |──── TRAIN 6m ────|── TEST 2m ──|
                          |──── TRAIN 6m ────|── TEST 2m ──|

Uso desde CLI:
    python tests/backtest_runner.py --symbol EURUSD --walkforward

Uso programático:
    from core.walkforward import WalkForwardTester
    wf = WalkForwardTester(train_bars=4320, test_bars=720, step_bars=720)
    report = wf.run(symbol='EURUSD', strategy='eurusd_asian_breakout',
                    total_bars=10000)
    print(report.summary())
"""

import logging
from dataclasses import dataclass, field
from typing import List, Optional, Dict
import pandas as pd

from strategies.base import resolve_required_history

logger = logging.getLogger(__name__)

# ── Constantes por defecto ────────────────────────────────────────────────────
# 720 H1 ≈ 1 mes | 4320 H1 ≈ 6 meses
DEFAULT_TRAIN_BARS = 4320   # 6 meses de entrenamiento
DEFAULT_TEST_BARS  = 720    # 1 mes de validación
DEFAULT_STEP_BARS  = 720    # avanzar 1 mes en cada iteración


# ── Estructuras de datos ──────────────────────────────────────────────────────

@dataclass
class WindowResult:
    """Resultado de una ventana TRAIN/TEST individual."""
    window_index:   int
    train_start:    int   # índice de barra en el df completo
    train_end:      int
    test_start:     int
    test_end:       int

    # Métricas TRAIN
    train_signals:  int   = 0
    train_winrate:  float = 0.0
    train_pf:       float = 0.0
    train_pips:     float = 0.0
    train_max_dd:   float = 0.0

    # Métricas TEST
    test_signals:   int   = 0
    test_winrate:   float = 0.0
    test_pf:        float = 0.0
    test_pips:      float = 0.0
    test_max_dd:    float = 0.0

    # Degradación (TEST vs TRAIN)
    pf_degradation:      float = 0.0   # train_pf - test_pf  (positivo = degradación)
    winrate_degradation: float = 0.0   # train_wr - test_wr
    consistency_score:   float = 0.0   # 0–1, mayor = más consistente


@dataclass
class WalkForwardReport:
    """Reporte completo del walk-forward testing."""
    symbol:         str
    strategy:       str
    train_bars:     int
    test_bars:      int
    step_bars:      int
    total_bars:     int
    windows:        List[WindowResult] = field(default_factory=list)

    # Métricas agregadas
    avg_train_pf:       float = 0.0
    avg_test_pf:        float = 0.0
    avg_pf_degradation: float = 0.0
    avg_winrate_train:  float = 0.0
    avg_winrate_test:   float = 0.0
    consistency_score:  float = 0.0   # promedio de consistency_score por ventana
    stability_rating:   str   = "UNKNOWN"  # STABLE / MARGINAL / UNSTABLE / OVERFITTED

    def summary(self) -> str:
        """Devuelve un resumen legible del walk-forward."""
        lines = [
            f"{'═'*65}",
            f"  WALK-FORWARD: {self.symbol} · {self.strategy}",
            f"{'═'*65}",
            f"  Ventanas analizadas : {len(self.windows)}",
            f"  Train / Test / Step : {self.train_bars} / {self.test_bars} / {self.step_bars} velas",
            f"",
            f"  {'Ventana':>8}  {'PF Train':>9}  {'PF Test':>9}  {'Degradación':>12}  {'WR Train':>9}  {'WR Test':>9}",
            f"  {'─'*63}",
        ]
        for w in self.windows:
            deg_str = f"{w.pf_degradation:+.2f}"
            deg_icon = "✅" if w.pf_degradation < 0.2 else ("⚠️" if w.pf_degradation < 0.5 else "❌")
            lines.append(
                f"  {w.window_index:>8}  "
                f"{w.train_pf:>9.2f}  "
                f"{w.test_pf:>9.2f}  "
                f"{deg_str:>10} {deg_icon}  "
                f"{w.train_winrate:>8.1f}%  "
                f"{w.test_winrate:>8.1f}%"
            )
        lines += [
            f"  {'─'*63}",
            f"  Promedio TRAIN      : PF {self.avg_train_pf:.2f} · WR {self.avg_winrate_train:.1f}%",
            f"  Promedio TEST       : PF {self.avg_test_pf:.2f} · WR {self.avg_winrate_test:.1f}%",
            f"  Degradación media   : {self.avg_pf_degradation:+.2f} PF",
            f"  Consistency score   : {self.consistency_score:.2f} / 1.00",
            f"",
            f"  Veredicto: {self._rating_icon()} {self.stability_rating}",
            f"{'═'*65}",
        ]
        return "\n".join(lines)

    def _rating_icon(self) -> str:
        return {"STABLE": "✅", "MARGINAL": "⚠️", "UNSTABLE": "❌", "OVERFITTED": "🔴"}.get(
            self.stability_rating, "❓"
        )

    def to_dict(self) -> Dict:
        """Serializa el reporte a dict para CSV/JSON."""
        return {
            'symbol':              self.symbol,
            'strategy':            self.strategy,
            'train_bars':          self.train_bars,
            'test_bars':           self.test_bars,
            'windows':             len(self.windows),
            'avg_train_pf':        round(self.avg_train_pf, 3),
            'avg_test_pf':         round(self.avg_test_pf, 3),
            'avg_pf_degradation':  round(self.avg_pf_degradation, 3),
            'avg_winrate_train':   round(self.avg_winrate_train, 2),
            'avg_winrate_test':    round(self.avg_winrate_test, 2),
            'consistency_score':   round(self.consistency_score, 3),
            'stability_rating':    self.stability_rating,
        }


# ── Motor principal ───────────────────────────────────────────────────────────

class WalkForwardTester:
    """
    Ejecuta walk-forward testing sobre datos históricos.

    Parámetros:
        train_bars:  Velas de entrenamiento por ventana (default 4320 ≈ 6 meses H1)
        test_bars:   Velas de validación por ventana   (default 720  ≈ 1 mes H1)
        step_bars:   Avance entre ventanas             (default 720  ≈ 1 mes H1)
        cb_losses:   Circuit breaker simulado (pérdidas consecutivas, 0=off)
        cb_pause:    Velas de pausa del CB
        lookback:    Ventana de indicadores del replay engine
    """

    def __init__(
        self,
        train_bars: int = DEFAULT_TRAIN_BARS,
        test_bars:  int = DEFAULT_TEST_BARS,
        step_bars:  int = DEFAULT_STEP_BARS,
        cb_losses:  int = 4,
        cb_pause:   int = 168,
        lookback:   Optional[int] = None,
    ):
        self.train_bars = train_bars
        self.test_bars  = test_bars
        self.step_bars  = step_bars
        self.cb_losses  = cb_losses
        self.cb_pause   = cb_pause
        self.lookback   = lookback

    def run(
        self,
        symbol:   str,
        strategy: str,
        total_bars: int = 10000,
        timeframe:  str = 'H1',
        config:     Dict = None,
        verbose:    bool = False,
    ) -> WalkForwardReport:
        """
        Descarga los datos una sola vez y ejecuta el walk-forward completo.

        Args:
            symbol:     Par a analizar
            strategy:   Nombre de la estrategia
            total_bars: Total de velas históricas a descargar
            timeframe:  Timeframe ('H1', 'H4', ...)
            config:     Configuración de la estrategia (opcional)
            verbose:    Si True, imprime progreso por ventana

        Returns:
            WalkForwardReport con todas las ventanas y métricas agregadas
        """
        from core.replay_engine import ReplayEngine
        from services.mt5_client import get_candles, initialize as mt5_initialize
        import MetaTrader5 as mt5

        strategy_instance = None
        try:
            from signals import STRATEGY_REGISTRY
            factory = STRATEGY_REGISTRY.get(strategy)
            if factory is not None:
                strategy_instance = factory()
        except Exception:
            strategy_instance = None

        resolved_lookback = self.lookback if self.lookback is not None else resolve_required_history(strategy_instance, fallback_required_history=200)
        self.lookback = resolved_lookback

        report = WalkForwardReport(
            symbol=symbol, strategy=strategy,
            train_bars=self.train_bars, test_bars=self.test_bars,
            step_bars=self.step_bars, total_bars=total_bars,
        )

        # ── 1. Descargar datos una sola vez ───────────────────────────────────
        logger.info(f"[WF] Descargando {total_bars + self.lookback} velas para {symbol}...")
        try:
            mt5_initialize()
            tf_map = {
                'H1': mt5.TIMEFRAME_H1, 'H4': mt5.TIMEFRAME_H4,
                'D1': mt5.TIMEFRAME_D1, 'M15': mt5.TIMEFRAME_M15,
            }
            mt5_tf = tf_map.get(timeframe.upper(), mt5.TIMEFRAME_H1)
            df_full = get_candles(symbol, mt5_tf, total_bars + self.lookback)
        except Exception as e:
            logger.error(f"[WF] Error descargando datos: {e}")
            return report

        if df_full is None or len(df_full) < self.lookback + self.train_bars + self.test_bars:
            logger.error(f"[WF] Datos insuficientes: {len(df_full) if df_full is not None else 0} velas")
            return report

        df_full = df_full.reset_index(drop=True)
        n = len(df_full)
        logger.info(f"[WF] {n} velas descargadas. Iniciando ventanas...")

        # ── 2. Generar ventanas ───────────────────────────────────────────────
        window_idx = 0
        start = 0  # inicio del bloque TRAIN (sin lookback)

        while True:
            train_start = start
            train_end   = start + self.train_bars
            test_start  = train_end
            test_end    = test_start + self.test_bars

            # Necesitamos lookback extra antes de cada ventana
            if train_start < self.lookback:
                start += self.step_bars
                continue
            if test_end + self.lookback > n:
                break  # no hay suficientes datos para esta ventana

            window_idx += 1
            if verbose:
                print(f"  [WF] Ventana {window_idx}: train [{train_start}:{train_end}] "
                      f"test [{test_start}:{test_end}]")

            # ── 3. Ejecutar TRAIN ─────────────────────────────────────────────
            # El lookback se toma de las velas anteriores al inicio del train
            df_train = df_full.iloc[train_start - self.lookback : train_end].copy()
            train_stats, train_signals = self._run_window(
                df_train, symbol, strategy, config,
                bars=self.train_bars, label=f"TRAIN-{window_idx}",
                timeframe=timeframe,
            )

            # ── 4. Ejecutar TEST ──────────────────────────────────────────────
            df_test = df_full.iloc[test_start - self.lookback : test_end].copy()
            test_stats, test_signals = self._run_window(
                df_test, symbol, strategy, config,
                bars=self.test_bars, label=f"TEST-{window_idx}",
                timeframe=timeframe,
            )

            # ── 5. Calcular métricas de la ventana ────────────────────────────
            train_pf = self._profit_factor(train_signals)
            test_pf  = self._profit_factor(test_signals)
            train_wr = train_stats.winrate
            test_wr  = test_stats.winrate

            # Degradación: cuánto cae el PF del train al test
            pf_deg = train_pf - test_pf
            wr_deg = train_wr - test_wr

            # Consistency score: 1 si test ≥ train, 0 si test = 0
            if train_pf > 0:
                consistency = max(0.0, min(1.0, test_pf / train_pf))
            else:
                consistency = 0.0

            wr = WindowResult(
                window_index=window_idx,
                train_start=train_start, train_end=train_end,
                test_start=test_start,   test_end=test_end,
                train_signals=train_stats.signals_final,
                train_winrate=train_wr,
                train_pf=train_pf,
                train_pips=train_stats.total_pips,
                train_max_dd=self._max_drawdown(train_signals),
                test_signals=test_stats.signals_final,
                test_winrate=test_wr,
                test_pf=test_pf,
                test_pips=test_stats.total_pips,
                test_max_dd=self._max_drawdown(test_signals),
                pf_degradation=pf_deg,
                winrate_degradation=wr_deg,
                consistency_score=consistency,
            )
            report.windows.append(wr)

            start += self.step_bars

        # ── 6. Calcular métricas agregadas ────────────────────────────────────
        self._aggregate(report)
        logger.info(f"[WF] Completado: {len(report.windows)} ventanas · {report.stability_rating}")
        return report

    # ── Helpers internos ──────────────────────────────────────────────────────

    def _run_window(self, df_window, symbol, strategy, config, bars, label='',
                    timeframe: str = 'H1'):
        """Ejecuta el replay engine sobre una ventana de datos ya descargados."""
        from core.replay_engine import ReplayEngine
        from core.engine import get_trading_engine

        max_forward = getattr(self, 'max_forward_bars', 120)
        get_trading_engine().reset_replay_state(symbol)

        engine = ReplayEngine(
            lookback_window=self.lookback,
            max_forward_bars=max_forward,
            cb_consecutive_losses=self.cb_losses,
            cb_pause_bars=self.cb_pause,
        )
        try:
            stats = engine.run_replay(
                symbol=symbol,
                bars=bars,
                strategy=strategy,
                config=config,
                skip_duplicate_filter=True,
                df_override=df_window,
                timeframe=timeframe,
            )
            return stats, engine.get_signals()
        except Exception as e:
            logger.warning(f"[WF] Error en ventana {label}: {e}")
            from core.replay_engine import ReplayStatistics
            return ReplayStatistics(), []

    @staticmethod
    def _profit_factor(signals) -> float:
        wins   = sum(s.profit_pips or 0 for s in signals if s.result == 'WIN')
        losses = abs(sum(s.profit_pips or 0 for s in signals if s.result == 'LOSS'))
        return wins / losses if losses > 0 else (float('inf') if wins > 0 else 0.0)

    @staticmethod
    def _max_drawdown(signals) -> float:
        equity = peak = dd = 0.0
        for s in signals:
            if s.result in ('WIN', 'LOSS'):
                equity += s.profit_pips or 0
                if equity > peak:
                    peak = equity
                dd = max(dd, peak - equity)
        return dd

    @staticmethod
    def _aggregate(report: WalkForwardReport):
        """Calcula métricas agregadas y el stability_rating."""
        if not report.windows:
            return

        n = len(report.windows)
        report.avg_train_pf       = sum(w.train_pf for w in report.windows) / n
        report.avg_test_pf        = sum(w.test_pf  for w in report.windows) / n
        report.avg_pf_degradation = sum(w.pf_degradation for w in report.windows) / n
        report.avg_winrate_train  = sum(w.train_winrate for w in report.windows) / n
        report.avg_winrate_test   = sum(w.test_winrate  for w in report.windows) / n
        report.consistency_score  = sum(w.consistency_score for w in report.windows) / n

        # Ventanas con test_pf > 1.0 (rentables en validación)
        profitable_windows = sum(1 for w in report.windows if w.test_pf >= 1.0)
        profitable_ratio   = profitable_windows / n

        # Stability rating
        avg_deg = report.avg_pf_degradation
        cons    = report.consistency_score
        test_pf = report.avg_test_pf

        if test_pf >= 1.2 and avg_deg < 0.3 and cons >= 0.7 and profitable_ratio >= 0.7:
            report.stability_rating = "STABLE"
        elif test_pf >= 1.0 and avg_deg < 0.6 and cons >= 0.5 and profitable_ratio >= 0.5:
            report.stability_rating = "MARGINAL"
        elif report.avg_train_pf >= 1.3 and test_pf < 1.0:
            report.stability_rating = "OVERFITTED"
        else:
            report.stability_rating = "UNSTABLE"
