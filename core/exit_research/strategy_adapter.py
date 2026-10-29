"""
Exit Research — Strategy Adapter
core/exit_research/strategy_adapter.py

Desacopla ExitResearchRunner de cualquier estrategia concreta.
Cualquier BaseStrategy puede ser envuelta en un StrategyAdapter
para ser usada por el runner sin modificar el código de la estrategia.

Uso:
    from strategies.eurusd import EURUSDStrategy
    from core.exit_research.strategy_adapter import StrategyAdapter

    adapter = StrategyAdapter(EURUSDStrategy())
    runner  = ExitResearchRunner(strategy=adapter)

También disponible el helper de conveniencia:
    from core.exit_research.strategy_adapter import adapter_for_symbol
    adapter = adapter_for_symbol("EURUSD")
"""

from __future__ import annotations

import importlib
import sys
import logging
from typing import Dict, Optional, TYPE_CHECKING

import pandas as pd

if TYPE_CHECKING:
    from strategies.base import BaseStrategy

logger = logging.getLogger(__name__)

# ── Mapa símbolo / estrategia → módulo + clase ─────────────────────────────
# Añadir aquí cuando se registren nuevas estrategias.
_STRATEGY_REGISTRY: Dict[str, tuple[str, str]] = {
    # symbol_key / strategy_key : (module_path,                 class_name)
    "EURUSD"                    : ("strategies.eurusd",          "EURUSDPartialStrategy"),
    "EURUSD_PARTIAL"            : ("strategies.eurusd",          "EURUSDPartialStrategy"),
    "EURUSD_SIMPLE"             : ("strategies.eurusd",          "EURUSDStrategy"),
    "XAUUSD"                    : ("strategies.xauusd_partial",  "XAUUSDPartialStrategy"),
    "XAUUSD_PARTIAL"            : ("strategies.xauusd_partial",  "XAUUSDPartialStrategy"),
    "XAUUSD_SIMPLE"             : ("strategies.xauusd",          "XAUUSDStrategy"),
    "BTCEUR"                    : ("strategies.btceur_partial",  "BTCEURPartialStrategy"),
    "BTCEUR_PARTIAL"            : ("strategies.btceur_partial",  "BTCEURPartialStrategy"),
    "BTCEUR_SIMPLE"             : ("strategies.btceur_new",      "BTCEURStrategy"),
    "BTC_TREND_PULLBACK_V1"     : ("strategies.btc_trend_pullback_v1", "BTCTrendPullbackV1Strategy"),
    "BTCEUR_REGIME_MOMENTUM"    : ("strategies.btceur_regime_momentum", "BTCEURRegimeMomentumStrategy"),
    "BTCEUR_WEEKLY_BREAKOUT"    : ("strategies.btceur_weekly_breakout", "BTCEURWeeklyBreakoutStrategy"),
    "EURUSD_FLOW"               : ("strategies.eurusd_flow", "EURUSDFlowStrategy"),
    "XAUUSD_SURGE"              : ("strategies.xauusd_surge", "XAUUSDSurgeStrategy"),
    "BTCEUR_TREND_SURGE"        : ("strategies.btceur_trend_surge", "BTCEURTrendSurgeStrategy"),
    "XAUUSD_GSRS"               : ("strategies.experimental.gold_newstrat", "XAUUSDGSRSStrategy"),
    "XAUUSD_ASIAN_LONDON"       : ("strategies.xauusd_asian_london", "XAUUSDAsianLondonStrategy"),
}


class StrategyAdapter:
    """
    Envuelve cualquier BaseStrategy para ExitResearchRunner.

    El adapter expone una única interfaz:
        get_signal(df_window) -> Optional[Dict]
    que llama a strategy.add_indicators() + strategy.detect_setup()
    usando la config almacenada.

    Los niveles SL/TP que devuelve la estrategia son ignorados por el runner:
    las variantes de salida calculan sus propios niveles.
    Lo que importa es únicamente la señal de DIRECCIÓN (BUY / SELL).
    """

    def __init__(
        self,
        strategy: "BaseStrategy",
        config: Optional[Dict] = None,
    ) -> None:
        """
        Args:
            strategy: Instancia de cualquier BaseStrategy.
            config:   Config de detección de señales. Si None usa
                      strategy._get_default_config().
        """
        self.strategy = strategy
        self.config   = config if config is not None else strategy._get_default_config()
        self.name     = getattr(strategy, "name", strategy.__class__.__name__)

    # ── API pública ───────────────────────────────────────────────────────────

    def get_signal(self, df_window: pd.DataFrame) -> Optional[Dict]:
        """
        Añade indicadores y detecta setup sobre la ventana dada.

        Returns:
            Dict de señal (con al menos 'type', 'entry', 'sl', 'tp')
            o None si no hay setup.
        """
        try:
            df = self.strategy.add_indicators(df_window.copy(), self.config)
            return self.strategy.detect_setup(df, self.config)
        except Exception as e:
            logger.debug("[StrategyAdapter] get_signal error (%s): %s", self.name, e)
            return None

    def get_atr(self, df_window: pd.DataFrame) -> float:
        """
        Extrae el ATR de la última fila después de añadir indicadores.
        Fallback: rango promedio de las últimas 14 velas.
        """
        try:
            df = self.strategy.add_indicators(df_window.copy(), self.config)
            if "atr" in df.columns:
                val = df["atr"].iloc[-1]
                if pd.notna(val) and float(val) > 0:
                    return float(val)
        except Exception:
            pass
        # Fallback: media del rango H/L de las últimas 14 velas
        try:
            return float((df_window["high"] - df_window["low"]).tail(14).mean())
        except Exception:
            return 0.001

    # ── Retrocompatibilidad ───────────────────────────────────────────────────

    def reload(self) -> None:
        """
        Fuerza la recarga del módulo de la estrategia (hot-reload).
        Útil si strategies/eurusd.py fue editado mientras el runner corre.
        """
        module_name = self.strategy.__class__.__module__
        if module_name in sys.modules:
            try:
                importlib.reload(sys.modules[module_name])
                logger.debug("[StrategyAdapter] Módulo %s recargado.", module_name)
            except Exception as e:
                logger.error(
                    "[StrategyAdapter] Error recargando %s: %s", module_name, e
                )
                raise

    def __repr__(self) -> str:
        return f"StrategyAdapter(strategy={self.name!r})"


# ── Factory ───────────────────────────────────────────────────────────────────

def adapter_for_strategy(
    strategy_name: str,
    symbol: Optional[str] = None,
    config: Optional[Dict] = None,
) -> StrategyAdapter:
    """
    Crea un StrategyAdapter para la estrategia o símbolo dado usando el registro interno.
    """
    key = strategy_name.upper().strip()
    if key not in _STRATEGY_REGISTRY and symbol:
        key = symbol.upper().strip()

    if key not in _STRATEGY_REGISTRY:
        # Fallback dinámico a estrategias del Vault o promovidas en strategies.STRATEGY_REGISTRY
        try:
            from strategies import STRATEGY_REGISTRY as GLOBAL_REG
            candidate_cls = GLOBAL_REG.get(key) or GLOBAL_REG.get(strategy_name.lower())
            if candidate_cls is not None:
                return StrategyAdapter(candidate_cls(), config=config)
        except Exception:
            pass

        registered = ", ".join(sorted(_STRATEGY_REGISTRY.keys()))
        raise ValueError(
            f"Estrategia o símbolo '{strategy_name}' no registrado. Disponibles: {registered}"
        )

    module_path, class_name = _STRATEGY_REGISTRY[key]

    try:
        module = importlib.import_module(module_path)
    except ImportError as e:
        raise ImportError(
            f"No se pudo importar '{module_path}' para '{key}': {e}"
        ) from e

    try:
        strategy_cls = getattr(module, class_name)
    except AttributeError as e:
        raise AttributeError(
            f"Clase '{class_name}' no encontrada en '{module_path}': {e}"
        ) from e

    return StrategyAdapter(strategy_cls(), config=config)


def adapter_for_symbol(
    symbol: str,
    config: Optional[Dict] = None,
) -> StrategyAdapter:
    """
    Crea un StrategyAdapter para el símbolo dado usando el registro interno.
    """
    return adapter_for_strategy(strategy_name=symbol, symbol=symbol, config=config)

