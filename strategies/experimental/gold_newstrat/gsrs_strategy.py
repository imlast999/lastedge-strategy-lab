"""
GSRS - Gold Session Reversal Strategy
======================================
Implementación e integración oficial para el laboratorio de estrategias de LastEdge.

Ver GSRS_spec_bot_backtest.md para el detalle completo de qué está
confirmado, qué es un supuesto (marcado aquí como ASSUMPTION) y qué
falta por definir.
"""

from dataclasses import dataclass, field
from datetime import datetime, time, timezone, timedelta
from enum import Enum, auto
from typing import Optional, List, Dict, Tuple
import pandas as pd
import numpy as np

try:
    from strategies.base import BaseStrategy, StrategyMetadata
except ImportError:
    try:
        from base import BaseStrategy, StrategyMetadata
    except ImportError:
        BaseStrategy = object
        StrategyMetadata = object


# ---------------------------------------------------------------------------
# 1. CONFIGURACION
# ---------------------------------------------------------------------------

@dataclass
class GSRSConfig:
    # --- Confirmado (ver doc SS2) ---
    symbol: str = "XAUUSD"
    entry_timeframe: str = "M1"
    context_timeframe: str = "H1"

    # --- Sesiones -- BLOQUEANTE: confirmar contra el proveedor de datos ---
    session_windows_utc: Dict[str, Tuple[time, time]] = field(default_factory=lambda: {
        "asia_second_hour":   (time(0, 0), time(1, 0)),   # ASSUMPTION
        "london_second_hour": (time(8, 0), time(9, 0)),   # ASSUMPTION
    })

    # --- Expansión inicial -- sin cuantificar por el autor ---
    expansion_min_atr_multiple: float = 1.5      # ASSUMPTION
    expansion_lookback_minutes: int = 10          # ASSUMPTION
    atr_period: int = 14                           # ASSUMPTION

    # --- Type 3 Shift / MSS -- reforzado por evidencia de vídeo (5 swings) ---
    swing_fractal_strength: int = 2                # ASSUMPTION (fractal estándar 5 velas)
    mss_required_swings: int = 5                   # evidencia de vídeo: L-H-HL-HH-break
    confirm_break_by: str = "close"                 # ASSUMPTION: "close" o "wick"

    # --- Pullback -- sin fórmula exacta confirmada ---
    pullback_fraction: float = 0.5                  # confirmado como cifra ("~50%")
    pullback_method: str = "simple_midpoint"          # ASSUMPTION: no se vio fibonacci en pantalla
    pullback_timeout_same_h1_candle: bool = True       # ASSUMPTION

    # --- Stop Loss -- confirmado en concepto, sin margen documentado ---
    sl_buffer_fraction_of_break: float = 0.10           # ASSUMPTION

    # --- Take Profit -- "50% de hourly overextension" ---
    tp_overextension_fraction: float = 0.5                # confirmado como cifra
    overextension_method: str = "h1_open_to_extreme"        # ASSUMPTION, apoyada por evidencia visual

    # --- Gestión de riesgo -- totalmente sin definir por el autor ---
    risk_percent_per_trade: float = 1.0                      # ASSUMPTION
    max_trades_per_session: int = 1                            # ASSUMPTION

    # --- Costes de operación -- necesarios para que el backtest sea realista ---
    spread_points: float = 25.0                                 # ASSUMPTION, ajustar a tu bróker
    commission_per_lot: float = 0.0                              # ASSUMPTION

    # --- Filtros -- sin definir por el autor ---
    news_filter_enabled: bool = False                             # ASSUMPTION
    min_atr_filter: Optional[float] = None                         # ASSUMPTION
    invalid_weekdays: List[int] = field(default_factory=list)      # ASSUMPTION, 0=lunes


# ---------------------------------------------------------------------------
# 2. ESTADOS Y ESTRUCTURAS DE DATOS
# ---------------------------------------------------------------------------

class GSRSState(Enum):
    WAIT_SESSION = auto()
    WAIT_SECOND_HOUR = auto()
    WAIT_EXPANSION = auto()
    WAIT_SHIFT = auto()
    WAIT_PULLBACK = auto()
    WAIT_ENTRY = auto()
    OPEN_POSITION = auto()
    MANAGE_POSITION = auto()
    POSITION_CLOSED = auto()


@dataclass
class Candle:
    time: datetime
    open: float
    high: float
    low: float
    close: float


@dataclass
class SwingPoint:
    index: int
    time: datetime
    price: float
    kind: str  # "low" | "high"


@dataclass
class TradeSetup:
    direction: str                  # "long" | "short"
    external_level: float            # nivel para el SL (swing "Higher High/Low" del shift)
    break_high: float
    break_low: float
    entry_price: Optional[float] = None
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None


# ---------------------------------------------------------------------------
# 3. MAQUINA DE ESTADOS
# ---------------------------------------------------------------------------

class GSRSStrategy:
    """
    Máquina de estados para GSRS. Cada método `_handle_XXX` corresponde a un
    estado de la máquina de estados descrita en la especificación.
    """

    def __init__(self, config: GSRSConfig):
        self.config = config
        self.state = GSRSState.WAIT_SESSION
        self.swings: List[SwingPoint] = []
        self.setup: Optional[TradeSetup] = None
        self.h1_open_price: Optional[float] = None
        self.h1_high_extreme: Optional[float] = None
        self.h1_low_extreme: Optional[float] = None
        self.session_candles: List[Candle] = []
        self.trades_this_session: int = 0

    # -- ciclo principal ----------------------------------------------------
    def on_new_candle(self, candle: Candle) -> None:
        """Se llama una vez por cada vela M1 cerrada."""
        handler = {
            GSRSState.WAIT_SESSION: self._handle_wait_session,
            GSRSState.WAIT_SECOND_HOUR: self._handle_wait_session,
            GSRSState.WAIT_EXPANSION: self._handle_wait_expansion,
            GSRSState.WAIT_SHIFT: self._handle_wait_shift,
            GSRSState.WAIT_PULLBACK: self._handle_wait_pullback,
            GSRSState.WAIT_ENTRY: self._handle_wait_entry,
            GSRSState.OPEN_POSITION: self._handle_open_position,
            GSRSState.MANAGE_POSITION: self._handle_manage_position,
            GSRSState.POSITION_CLOSED: self._handle_position_closed,
        }[self.state]
        handler(candle)

    # -- WAIT_SESSION / WAIT_SECOND_HOUR ------------------------------------
    def _handle_wait_session(self, candle: Candle) -> None:
        if self._in_second_hour_window(candle.time):
            self.h1_open_price = candle.open
            self.h1_high_extreme = candle.high
            self.h1_low_extreme = candle.low
            self.session_candles = [candle]
            self.state = GSRSState.WAIT_EXPANSION

    # -- WAIT_EXPANSION -------------------------------------------------------
    def _handle_wait_expansion(self, candle: Candle) -> None:
        self.session_candles.append(candle)
        self._update_h1_extreme(candle)

        if is_expansion_assumption(self.session_candles, self.config):
            self.state = GSRSState.WAIT_SHIFT

    # -- WAIT_SHIFT (Type 3 Shift / posible MSS) -------------------------------
    def _handle_wait_shift(self, candle: Candle) -> None:
        self.session_candles.append(candle)
        self._update_h1_extreme(candle)

        self.swings = detect_swings(self.session_candles, self.config)
        setup = check_type3_shift(self.swings)
        if setup is not None:
            self.setup = setup
            self.state = GSRSState.WAIT_PULLBACK

    # -- WAIT_PULLBACK ----------------------------------------------------------
    def _handle_wait_pullback(self, candle: Candle) -> None:
        assert self.setup is not None
        level = pullback_entry_level(self.setup, self.config)
        touched = (candle.low <= level <= candle.high)
        if touched:
            self.setup.entry_price = level
            self.state = GSRSState.WAIT_ENTRY

    # -- WAIT_ENTRY ---------------------------------------------------------------
    def _handle_wait_entry(self, candle: Candle) -> None:
        assert self.setup is not None
        self.setup.stop_loss = compute_stop_loss(self.setup, self.config)
        h1_extreme = self.h1_high_extreme if self.setup.direction == "short" else self.h1_low_extreme
        self.setup.take_profit = compute_take_profit(
            self.setup, self.h1_open_price, h1_extreme, self.config
        )
        self.state = GSRSState.OPEN_POSITION

    # -- OPEN_POSITION / MANAGE_POSITION -------------------------------------------
    def _handle_open_position(self, candle: Candle) -> None:
        self.state = GSRSState.MANAGE_POSITION

    def _handle_manage_position(self, candle: Candle) -> None:
        assert self.setup is not None
        hit_sl, hit_tp = check_sl_tp_hit(candle, self.setup)
        if hit_sl or hit_tp:
            self.trades_this_session += 1
            self.state = GSRSState.POSITION_CLOSED

    def _handle_position_closed(self, candle: Candle) -> None:
        self.setup = None
        if self.trades_this_session >= self.config.max_trades_per_session:
            self.state = GSRSState.WAIT_SESSION
        else:
            self.state = GSRSState.WAIT_SESSION

    # -- utilidades -----------------------------------------------------------------
    def _in_second_hour_window(self, ts: datetime) -> bool:
        if ts.tzinfo is None:
            t = ts.time()
        else:
            t = ts.astimezone(timezone.utc).time()
        for start, end in self.config.session_windows_utc.values():
            if start <= t < end:
                return True
        return False

    def _update_h1_extreme(self, candle: Candle) -> None:
        if self.h1_high_extreme is None:
            self.h1_high_extreme = candle.high
        else:
            self.h1_high_extreme = max(self.h1_high_extreme, candle.high)

        if self.h1_low_extreme is None:
            self.h1_low_extreme = candle.low
        else:
            self.h1_low_extreme = min(self.h1_low_extreme, candle.low)


# ---------------------------------------------------------------------------
# 4. FUNCIONES DE APOYO (implementaciones ASSUMPTION / FRACTALES)
# ---------------------------------------------------------------------------

def is_expansion_assumption(candles: List[Candle], config: GSRSConfig) -> bool:
    """
    ASSUMPTION: expansión = rango de las últimas N velas >= X * un proxy de ATR.
    """
    window = candles[-config.expansion_lookback_minutes:]
    if len(window) < 2:
        return False
    move = abs(window[-1].close - window[0].open)
    proxy_atr = sum(c.high - c.low for c in window) / len(window)
    if proxy_atr == 0:
        return False
    return move >= config.expansion_min_atr_multiple * proxy_atr


def detect_swings(candles: List[Candle], config: GSRSConfig) -> List[SwingPoint]:
    """
    Detección de fractales/pivotes sobre `candles` usando config.swing_fractal_strength
    (número de velas a cada lado que deben ser más bajas/altas para confirmar un pivote).
    """
    n = config.swing_fractal_strength
    if len(candles) < 2 * n + 1:
        return []

    swings: List[SwingPoint] = []
    for i in range(n, len(candles) - n):
        c = candles[i]
        is_high = (
            all(c.high > candles[i - k].high for k in range(1, n + 1)) and
            all(c.high > candles[i + k].high for k in range(1, n + 1))
        )
        is_low = (
            all(c.low < candles[i - k].low for k in range(1, n + 1)) and
            all(c.low < candles[i + k].low for k in range(1, n + 1))
        )

        if is_high:
            swings.append(SwingPoint(index=i, time=c.time, price=c.high, kind="high"))
        if is_low:
            swings.append(SwingPoint(index=i, time=c.time, price=c.low, kind="low"))

    return swings


def check_type3_shift(swings: List[SwingPoint]) -> Optional[TradeSetup]:
    """
    Comprueba la secuencia de 5 puntos observada en el vídeo:
    - Bajista (Short): Low1 -> High1 -> Low2 (HL) -> High2 (HH) -> Low3 (< Low1)
    - Alcista (Long):  High1 -> Low1 -> High2 (LH) -> Low2 (LL) -> High3 (> High1)
    """
    if len(swings) < 5:
        return None
    s1, s2, s3, s4, s5 = swings[-5:]

    bearish_shift = (
        s1.kind == "low" and s2.kind == "high" and s3.kind == "low"
        and s4.kind == "high" and s5.kind == "low"
        and s3.price > s1.price and s4.price > s2.price and s5.price < s1.price
    )
    if bearish_shift:
        return TradeSetup(
            direction="short",
            external_level=s4.price,   # External High (H2) -> referencia para el SL
            break_high=s4.price,
            break_low=s5.price,
        )

    bullish_shift = (
        s1.kind == "high" and s2.kind == "low" and s3.kind == "high"
        and s4.kind == "low" and s5.kind == "high"
        and s3.price < s1.price and s4.price < s2.price and s5.price > s1.price
    )
    if bullish_shift:
        return TradeSetup(
            direction="long",
            external_level=s4.price,   # External Low (L2) -> referencia para el SL
            break_high=s5.price,
            break_low=s4.price,
        )

    return None


def pullback_entry_level(setup: TradeSetup, config: GSRSConfig) -> float:
    """ASSUMPTION: punto medio simple del tramo de ruptura (sin fibonacci visible)."""
    if config.pullback_method != "simple_midpoint":
        raise NotImplementedError(f"Método de pullback no implementado: {config.pullback_method}")
    return setup.break_low + config.pullback_fraction * (setup.break_high - setup.break_low)


def compute_stop_loss(setup: TradeSetup, config: GSRSConfig) -> float:
    """Confirmado en concepto: SL más allá del nivel externo. Margen = ASSUMPTION."""
    break_range = setup.break_high - setup.break_low
    buffer_ = config.sl_buffer_fraction_of_break * break_range
    if setup.direction == "short":
        return setup.external_level + buffer_
    return setup.external_level - buffer_


def compute_take_profit(
    setup: TradeSetup, h1_open: Optional[float], h1_extreme: Optional[float], config: GSRSConfig
) -> float:
    """ASSUMPTION: overextension = |extremo_H1 - apertura_H1|; TP = 50% de esa distancia."""
    if h1_open is None or h1_extreme is None:
        raise ValueError("h1_open / h1_extreme no disponibles todavía")
    overextension = abs(h1_extreme - h1_open)
    tp_distance = config.tp_overextension_fraction * overextension
    if setup.direction == "short":
        return h1_open - tp_distance
    return h1_open + tp_distance


def check_sl_tp_hit(candle: Candle, setup: TradeSetup) -> Tuple[bool, bool]:
    if setup.stop_loss is None or setup.take_profit is None:
        return False, False
    if setup.direction == "short":
        hit_sl = candle.high >= setup.stop_loss
        hit_tp = candle.low <= setup.take_profit
    else:
        hit_sl = candle.low <= setup.stop_loss
        hit_tp = candle.high >= setup.take_profit
    return hit_sl, hit_tp


# ---------------------------------------------------------------------------
# 5. CLASE DE INTEGRACIÓN CON BASESTRATEGY
# ---------------------------------------------------------------------------

class XAUUSDGSRSStrategy(BaseStrategy):
    """
    Estrategia GSRS integrada con la interfaz BaseStrategy de LastEdge.
    Permite ejecutar GSRS desde ReplayEngine, WalkForwardTester, ExitResearch
    y el dispatcher de servicios (`detect_signal`).
    """

    required_timeframe: str = "M1"

    def __init__(self):
        self.gsrs_config = GSRSConfig()
        self.engine = GSRSStrategy(self.gsrs_config)
        super().__init__("xauusd_gsrs")

    @property
    def metadata(self) -> StrategyMetadata:
        return StrategyMetadata(
            required_history=120,
            symbol="XAUUSD",
            timeframe="M1",
            strategy_name=self.name,
            version="1.0-experimental",
        )

    def reset_state(self) -> None:
        self.engine = GSRSStrategy(self.gsrs_config)

    def _get_default_config(self) -> Dict:
        cfg = getattr(self, 'gsrs_config', None) or GSRSConfig()
        return {
            'symbol': cfg.symbol,
            'entry_timeframe': cfg.entry_timeframe,
            'context_timeframe': cfg.context_timeframe,
            'expansion_min_atr_multiple': cfg.expansion_min_atr_multiple,
            'expansion_lookback_minutes': cfg.expansion_lookback_minutes,
            'swing_fractal_strength': cfg.swing_fractal_strength,
            'mss_required_swings': cfg.mss_required_swings,
            'pullback_fraction': cfg.pullback_fraction,
            'sl_buffer_fraction_of_break': cfg.sl_buffer_fraction_of_break,
            'tp_overextension_fraction': cfg.tp_overextension_fraction,
            'risk_percent_per_trade': cfg.risk_percent_per_trade,
            'max_trades_per_session': cfg.max_trades_per_session,
        }

    def _add_specific_indicators(self, df: pd.DataFrame, config: Dict) -> pd.DataFrame:
        return df

    def detect_setup(self, df: pd.DataFrame, config: Dict = None) -> Optional[Dict]:
        if df is None or len(df) < 5:
            return None

        cfg_dict = {**self.default_config, **(config or {})}
        # Actualizar config de GSRS si se pasa configuración personalizada
        if 'swing_fractal_strength' in cfg_dict:
            self.gsrs_config.swing_fractal_strength = int(cfg_dict['swing_fractal_strength'])

        df_proc = df.copy()
        if 'time' in df_proc.columns:
            df_proc['time'] = pd.to_datetime(df_proc['time'])

        self.reset_state()

        candles: List[Candle] = []
        for idx, row in df_proc.iterrows():
            t = row['time'] if 'time' in row else datetime.now(timezone.utc)
            if hasattr(t, 'to_pydatetime'):
                t = t.to_pydatetime()
            elif isinstance(t, str):
                t = datetime.fromisoformat(t)

            c = Candle(
                time=t,
                open=float(row['open']),
                high=float(row['high']),
                low=float(row['low']),
                close=float(row['close']),
            )
            candles.append(c)
            self.engine.on_new_candle(c)

        if self.engine.state in (GSRSState.OPEN_POSITION, GSRSState.MANAGE_POSITION, GSRSState.WAIT_ENTRY) and self.engine.setup is not None:
            setup = self.engine.setup
            if setup.entry_price is None or setup.stop_loss is None or setup.take_profit is None:
                return None

            direction = 'BUY' if setup.direction == 'long' else 'SELL'
            sl_distance = abs(setup.entry_price - setup.stop_loss)
            tp_distance = abs(setup.take_profit - setup.entry_price)
            rr = tp_distance / sl_distance if sl_distance > 0 else 1.0

            return {
                'type': direction,
                'entry': setup.entry_price,
                'sl': setup.stop_loss,
                'tp': setup.take_profit,
                'timeframe': 'M1',
                'explanation': (
                    f"GSRS {direction} setup | Entry: {setup.entry_price:.2f} | "
                    f"SL: {setup.stop_loss:.2f} | TP: {setup.take_profit:.2f} | R:R={rr:.2f}"
                ),
                'expires': datetime.now(timezone.utc) + timedelta(minutes=60),
                'setup_strength': 0.75,
                'context': {
                    'strategy': 'xauusd_gsrs',
                    'direction': setup.direction,
                    'external_level': setup.external_level,
                    'break_high': setup.break_high,
                    'break_low': setup.break_low,
                    'risk_reward': rr,
                    'state': self.engine.state.name,
                }
            }
        return None
