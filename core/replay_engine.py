"""
Market Replay Engine - Sistema de Backtesting Rápido

Este módulo permite simular miles de velas históricas y ejecutar
las estrategias del bot sobre ellas para validar el comportamiento
sin esperar días de mercado real.

IMPORTANTE: Reutiliza el mismo pipeline de producción:
- Estrategias actuales
- Engine actual
- Scoring actual
- Filtros actuales (excepto duplicados en modo diagnóstico)
"""

import logging
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field
import pandas as pd

from strategies.base import resolve_required_history

logger = logging.getLogger(__name__)

@dataclass
class ReplaySignal:
    """Señal detectada durante el replay"""
    timestamp: datetime
    symbol: str
    signal_type: str  # BUY/SELL
    entry: float
    sl: float
    tp: float
    confidence: str
    score: float
    bar_index: int
    
    # Resultado de simulación TP/SL
    result: Optional[str] = None  # WIN/LOSS/PENDING
    exit_price: Optional[float] = None
    exit_bar: Optional[int] = None
    profit_pips: Optional[float] = None

@dataclass
class ReplayStatistics:
    """Estadísticas del replay"""
    bars_analyzed: int = 0
    setups_detected: int = 0
    signals_final: int = 0
    buy_signals: int = 0
    sell_signals: int = 0
    tp_hits: int = 0
    sl_hits: int = 0
    pending: int = 0
    winrate: float = 0.0
    avg_rr: float = 0.0
    total_pips: float = 0.0
    execution_time: float = 0.0
    # Circuit breaker simulado
    cb_activations: int = 0        # veces que se activó el CB
    bars_paused: int = 0           # velas totales en pausa por CB
    signals_blocked_by_cb: int = 0 # señales que habrían salido pero el CB las bloqueó

class ReplayEngine:
    """
    Motor de replay que ejecuta estrategias sobre datos históricos
    
    Características:
    - Reutiliza el pipeline completo de producción
    - Simula TP/SL para calcular winrate
    - Genera estadísticas detalladas
    - Modo diagnóstico (sin filtro de duplicados)
    """
    
    def __init__(self, lookback_window: Optional[int] = None, max_forward_bars: int = 120,
                 cb_consecutive_losses: int = 4, cb_pause_bars: int = 168):
        """
        Args:
            lookback_window:       Número de velas a usar para análisis de indicadores
            max_forward_bars:      Máximo de velas a revisar hacia adelante para TP/SL
            cb_consecutive_losses: Pérdidas consecutivas para activar el circuit breaker
                                   (0 = desactivado)
            cb_pause_bars:         Velas de pausa tras activar el CB
                                   (168 H1 ≈ 1 semana; 24 H1 ≈ 1 día)
        """
        self.lookback_window = lookback_window
        self.max_forward_bars = max_forward_bars
        self.cb_consecutive_losses = cb_consecutive_losses
        self.cb_pause_bars = cb_pause_bars
        self.signals: List[ReplaySignal] = []
        
    def run_replay(self, symbol: str, bars: int, strategy: str = None,
                   config: Dict = None, skip_duplicate_filter: bool = True,
                   timeframe: str = 'H1',
                   df_override: 'pd.DataFrame' = None) -> 'ReplayStatistics':
        """
        Ejecuta replay sobre datos históricos.

        Args:
            symbol:               Símbolo a analizar (EURUSD, XAUUSD, BTCEUR)
            bars:                 Número de velas históricas a analizar
            strategy:             Estrategia a usar (None = auto-detectar por símbolo)
            config:               Configuración específica (opcional)
            skip_duplicate_filter: Si True, omite filtro de duplicados
            timeframe:            Timeframe de las velas ('H1', 'H4', etc.)
            df_override:          DataFrame ya descargado. Si se pasa, se omite la
                                  descarga de MT5. Útil para walk-forward (descarga
                                  una sola vez y divide en ventanas).

        Returns:
            ReplayStatistics con resultados completos
        """
        import time
        from services.mt5_client import get_candles, initialize as mt5_initialize
        import MetaTrader5 as mt5
        from core.engine import get_trading_engine
        
        start_time = time.time()
        
        try:
            # Auto-detectar estrategia si no se especifica
            if strategy is None:
                strategy = self._auto_detect_strategy(symbol)
            
            # Resolver timeframe efectivo ANTES de descargar datos:
            # si la estrategia declara required_timeframe, usar ese; si no, usar el timeframe pasado.
            effective_timeframe = timeframe
            try:
                from signals import STRATEGY_REGISTRY
                factory = STRATEGY_REGISTRY.get(strategy)
                if factory is not None:
                    strategy_instance = factory()
                    if hasattr(strategy_instance, 'required_timeframe') and strategy_instance.required_timeframe:
                        effective_timeframe = strategy_instance.required_timeframe
                        logger.info(f"[WF] Estrategia '{strategy}' requiere timeframe '{effective_timeframe}'")
            except Exception as e:
                logger.debug(f"No se pudo resolver required_timeframe para '{strategy}': {e}")
            
            logger.info(f"Usando estrategia: {strategy} | timeframe efectivo: {effective_timeframe}")

            strategy_instance_for_history = None
            try:
                from signals import STRATEGY_REGISTRY
                factory = STRATEGY_REGISTRY.get(strategy)
                if factory is not None:
                    strategy_instance_for_history = factory()
            except Exception as e:
                logger.debug(f"No se pudo instanciar estrategia para history check: {e}")

            required_history = resolve_required_history(strategy_instance_for_history, fallback_required_history=200)
            effective_lookback = self.lookback_window if self.lookback_window is not None else required_history
            self.lookback_window = effective_lookback
            logger.info(f"Lookback efectivo para {strategy}: {self.lookback_window} (requerida por metadata={required_history})")
            
            # ── Obtener datos históricos ──────────────────────────────────────
            if df_override is not None:
                # Datos ya proporcionados externamente (walk-forward, etc.)
                df_full = df_override.reset_index(drop=True)
                logger.info(f"Usando df_override: {len(df_full)} velas para {symbol}")
            else:
                # Descargar desde MT5
                mt5_initialize()
                total_bars_needed = self.lookback_window + bars
                logger.info(f"Cargando {total_bars_needed} velas para {symbol}...")

                tf_map = {
                    'H1': mt5.TIMEFRAME_H1,
                    'H4': mt5.TIMEFRAME_H4,
                    'D1': mt5.TIMEFRAME_D1,
                    'M15': mt5.TIMEFRAME_M15,
                    'M5': mt5.TIMEFRAME_M5,
                }
                mt5_timeframe = tf_map.get(effective_timeframe.upper(), mt5.TIMEFRAME_H1)
                df_full = get_candles(symbol, mt5_timeframe, total_bars_needed)

            if df_full is None or len(df_full) < self.lookback_window + 10:
                logger.error(f"Datos insuficientes para {symbol}: {len(df_full) if df_full is not None else 0} velas")
                return ReplayStatistics()
            
            logger.info(f"Datos cargados: {len(df_full)} velas")
            
            # Obtener engine (estado limpio por cada run_replay / ventana WF)
            engine = get_trading_engine()
            engine.reset_replay_state(symbol)

            # Estadísticas
            stats = ReplayStatistics()
            self.signals = []

            # ── Circuit breaker simulado ──────────────────────────────────────
            cb_enabled          = self.cb_consecutive_losses > 0
            cb_consecutive      = 0    # pérdidas consecutivas actuales
            cb_paused_until_bar = -1   # índice de vela hasta la que está pausado

            # Recorrer velas una a una
            bars_to_analyze = min(bars, len(df_full) - self.lookback_window)
            logger.info(f"Analizando {bars_to_analyze} velas...")
            
            for i in range(self.lookback_window, self.lookback_window + bars_to_analyze):

                # ── Verificar si el CB está activo ────────────────────────────
                if cb_enabled and i <= cb_paused_until_bar:
                    stats.bars_paused += 1
                    stats.bars_analyzed += 1
                    # Comprobar si habría habido señal (para contabilizar bloqueadas)
                    window = df_full.iloc[i - self.lookback_window:i].copy()
                    result = engine.evaluate_signal(
                        window, symbol, strategy, config,
                        skip_duplicate_filter=skip_duplicate_filter,
                        current_index=i
                    )
                    if result.signal and result.should_show:
                        stats.signals_blocked_by_cb += 1
                    continue

                # Crear ventana de análisis (últimas lookback_window velas)
                window = df_full.iloc[i - self.lookback_window:i].copy()
                
                # Evaluar señal usando el engine completo
                # Para backtest: pasar el timestamp de la vela actual para que el
                # filtro de duplicados use la fecha histórica y no datetime.now().
                current_bar_time = None
                if 'time' in window.columns:
                    try:
                        current_bar_time = pd.to_datetime(window.iloc[-1]['time'])
                        if current_bar_time.tzinfo is None:
                            current_bar_time = current_bar_time.replace(tzinfo=timezone.utc)
                    except Exception:
                        current_bar_time = None
                
                result = engine.evaluate_signal(
                    window, 
                    symbol, 
                    strategy, 
                    config,
                    skip_duplicate_filter=skip_duplicate_filter,
                    current_index=i,
                    current_bar_time=current_bar_time,
                )
                
                stats.bars_analyzed += 1
                
                # Contar setups
                if result.signal is not None:
                    stats.setups_detected += 1
                elif result.rejection_reason and result.rejection_reason not in [
                    "No setup básico detectado",
                    "Símbolo desactivado en configuración dinámica"
                ]:
                    stats.setups_detected += 1
                
                # Si hay señal final
                if result.signal and result.should_show:
                    stats.signals_final += 1
                    
                    signal_type = result.signal.get('type', 'BUY')
                    if signal_type == 'BUY':
                        stats.buy_signals += 1
                    else:
                        stats.sell_signals += 1
                    
                    # Crear registro de señal
                    replay_signal = ReplaySignal(
                        timestamp=df_full.iloc[i]['time'] if 'time' in df_full.columns else datetime.now(timezone.utc),
                        symbol=symbol,
                        signal_type=signal_type,
                        entry=float(result.signal.get('entry', 0)),
                        sl=float(result.signal.get('sl', 0)),
                        tp=float(result.signal.get('tp', 0)),
                        confidence=result.confidence,
                        score=result.score,
                        bar_index=i
                    )
                    
                    # Simular TP/SL en velas futuras
                    self._simulate_tp_sl(replay_signal, df_full, i)
                    
                    self.signals.append(replay_signal)
                    
                    # Actualizar estadísticas de resultados
                    if replay_signal.result == 'WIN':
                        stats.tp_hits += 1
                        stats.total_pips += replay_signal.profit_pips or 0
                        cb_consecutive = 0   # reset racha de pérdidas
                    elif replay_signal.result == 'LOSS':
                        stats.sl_hits += 1
                        stats.total_pips += replay_signal.profit_pips or 0
                        cb_consecutive += 1
                        # ── Activar CB si se alcanza el límite ────────────────
                        if cb_enabled and cb_consecutive >= self.cb_consecutive_losses:
                            cb_paused_until_bar = i + self.cb_pause_bars
                            stats.cb_activations += 1
                            logger.info(
                                "[CB_SIM] Activado tras %d pérdidas consecutivas en barra %d "
                                "| Pausa hasta barra %d (%d velas)",
                                cb_consecutive, i, cb_paused_until_bar, self.cb_pause_bars
                            )
                            cb_consecutive = 0   # reset para la siguiente ronda
                    else:
                        stats.pending += 1
            
            # Calcular métricas finales
            closed_trades = stats.tp_hits + stats.sl_hits
            if closed_trades > 0:
                stats.winrate = (stats.tp_hits / closed_trades) * 100
            
            # Calcular R:R promedio
            if stats.signals_final > 0:
                total_rr = 0
                for sig in self.signals:
                    risk = abs(sig.entry - sig.sl)
                    reward = abs(sig.tp - sig.entry)
                    if risk > 0:
                        total_rr += reward / risk
                stats.avg_rr = total_rr / stats.signals_final
            
            stats.execution_time = time.time() - start_time
            
            logger.info(f"Replay completado: {stats.signals_final} señales en {stats.execution_time:.2f}s")
            
            return stats
            
        except Exception as e:
            logger.error(f"Error en replay: {e}", exc_info=True)
            stats = ReplayStatistics()
            stats.execution_time = time.time() - start_time
            return stats
    
    def _auto_detect_strategy(self, symbol: str) -> str:
        """Auto-detecta estrategia basada en símbolo"""
        symbol_upper = symbol.upper()
        
        if symbol_upper == 'EURUSD':
            return 'eurusd_partial'
        elif symbol_upper == 'XAUUSD':
            return 'xauusd_partial'
        elif symbol_upper in ['BTCEUR', 'BTCUSDT']:
            return 'btceur_partial'
        else:
            return 'ema50_200'
    
    def _get_pip_size(self, symbol: str) -> float:
        """
        Obtiene el tamaño de pip correcto según el símbolo
        
        Args:
            symbol: Símbolo del instrumento
            
        Returns:
            Tamaño de pip para el símbolo
        """
        symbol_upper = symbol.upper()
        
        if symbol_upper == 'EURUSD':
            return 0.0001  # 1 pip = 0.0001
        elif symbol_upper == 'XAUUSD':
            return 0.1  # 1 pip = 0.1 en precio estándar
        elif symbol_upper in ['BTCEUR', 'BTCUSDT']:
            return 1.0  # 1 pip = 1.0
        else:
            # Default para pares Forex
            return 0.0001
    
    def _simulate_tp_sl(self, signal: ReplaySignal, df_full: pd.DataFrame, start_index: int):
        """
        Simula el resultado de una señal avanzando velas hasta TP o SL.
        Los profit_pips incluyen spread y comisión (costes reales de trading).
        """
        try:
            from core.trade_costs import apply_costs_to_profit
            pip_size = self._get_pip_size(signal.symbol)
            
            # Máximo de velas a revisar hacia adelante
            # H1: 120 velas = ~5 días | H4: 300 velas = ~50 días (swing trading)
            max_forward_bars = self.max_forward_bars
            
            for i in range(start_index + 1, min(start_index + max_forward_bars, len(df_full))):
                bar = df_full.iloc[i]
                high = float(bar['high'])
                low = float(bar['low'])
                
                if signal.signal_type == 'BUY':
                    # Verificar TP (precio sube)
                    if high >= signal.tp:
                        signal.result = 'WIN'
                        signal.exit_price = signal.tp
                        signal.exit_bar = i
                        raw_pips = (signal.tp - signal.entry) / pip_size
                        signal.profit_pips = apply_costs_to_profit(raw_pips, signal.symbol)
                        return
                    
                    # Verificar SL (precio baja)
                    if low <= signal.sl:
                        signal.result = 'LOSS'
                        signal.exit_price = signal.sl
                        signal.exit_bar = i
                        raw_pips = (signal.sl - signal.entry) / pip_size
                        signal.profit_pips = apply_costs_to_profit(raw_pips, signal.symbol)
                        return
                
                else:  # SELL
                    # Verificar TP (precio baja)
                    if low <= signal.tp:
                        signal.result = 'WIN'
                        signal.exit_price = signal.tp
                        signal.exit_bar = i
                        raw_pips = (signal.entry - signal.tp) / pip_size
                        signal.profit_pips = apply_costs_to_profit(raw_pips, signal.symbol)
                        return
                    
                    # Verificar SL (precio sube)
                    if high >= signal.sl:
                        signal.result = 'LOSS'
                        signal.exit_price = signal.sl
                        signal.exit_bar = i
                        raw_pips = (signal.entry - signal.sl) / pip_size
                        signal.profit_pips = apply_costs_to_profit(raw_pips, signal.symbol)
                        return
            
            # Si llegamos aquí, la señal sigue pendiente
            signal.result = 'PENDING'
            signal.exit_price = None
            signal.exit_bar = None
            signal.profit_pips = 0.0
            
        except Exception as e:
            logger.warning(f"Error simulando TP/SL: {e}")
            signal.result = 'ERROR'
    
    def get_signals(self) -> List[ReplaySignal]:
        """Obtiene lista de señales detectadas durante el replay"""
        return self.signals
    
    def get_detailed_report(self) -> str:
        """Genera reporte detallado en formato texto"""
        if not self.signals:
            return "No hay señales para reportar"
        
        lines = []
        lines.append("=" * 60)
        lines.append("REPORTE DETALLADO DE SEÑALES")
        lines.append("=" * 60)
        lines.append("")
        
        for i, sig in enumerate(self.signals, 1):
            lines.append(f"Señal #{i}")
            lines.append(f"  Timestamp: {sig.timestamp}")
            lines.append(f"  Tipo: {sig.signal_type}")
            lines.append(f"  Entry: {sig.entry:.5f}")
            lines.append(f"  SL: {sig.sl:.5f}")
            lines.append(f"  TP: {sig.tp:.5f}")
            lines.append(f"  Confianza: {sig.confidence} (Score: {sig.score:.2f})")
            lines.append(f"  Resultado: {sig.result or 'PENDING'}")
            if sig.exit_price:
                lines.append(f"  Exit: {sig.exit_price:.5f} (Bar {sig.exit_bar})")
                lines.append(f"  Profit: {sig.profit_pips:.1f} pips")
            lines.append("")
        
        return "\n".join(lines)


# Instancia global del replay engine
_replay_engine = None

def get_replay_engine(lookback_window: Optional[int] = None) -> ReplayEngine:
    """Obtiene instancia del replay engine"""
    global _replay_engine
    if _replay_engine is None:
        _replay_engine = ReplayEngine(lookback_window)
    return _replay_engine
