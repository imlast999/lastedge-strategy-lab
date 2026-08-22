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

# ── Mapa símbolo → módulo + clase ────────────────────────────────────────────
# Añadir aquí cuando se registren nuevas estrategias.
_STRATEGY_REGISTRY: Dict[str, tuple[str, str]] = {
    # symbol_key   : (module_path,                 class_name)
    "EURUSD"       : ("strategies.eurusd",          "EURUSDPartialStrategy"),
    "XAUUSD"       : ("strategies.xauusd_partial",  "XAUUSDPartialStrategy"),
    "BTCEUR"       : ("strategies.btceur_partial", "BTCEURPartialStrategy"),
    "XAUUSD_GSRS"  : ("strategies.experimental.gold_newstrat", "XAUUSDGSRSStrategy"),
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

def adapter_for_symbol(
    symbol: str,
    config: Optional[Dict] = None,
) -> StrategyAdapter:
    """
    Crea un StrategyAdapter para el símbolo dado usando el registro interno.

    Args:
        symbol: 'EURUSD', 'XAUUSD', 'BTCEUR' (case-insensitive).
        config: Config de detección. None = usar default de la estrategia.

    Returns:
        StrategyAdapter listo para usar.

    Raises:
        ValueError: Si el símbolo no está en el registro.
        ImportError / AttributeError: Si el módulo o clase no existen.
    """
    key = symbol.upper()
    if key not in _STRATEGY_REGISTRY:
        registered = ", ".join(_STRATEGY_REGISTRY.keys())
        raise ValueError(
            f"Símbolo '{symbol}' no registrado. Disponibles: {registered}"
        )

    module_path, class_name = _STRATEGY_REGISTRY[key]

    try:
        module = importlib.import_module(module_path)
    except ImportError as e:
        raise ImportError(
            f"No se pudo importar '{module_path}' para '{symbol}': {e}"
        ) from e

    try:
        strategy_cls = getattr(module, class_name)
    except AttributeError as e:
        raise AttributeError(
            f"Clase '{class_name}' no encontrada en '{module_path}': {e}"
        ) from e

    return StrategyAdapter(strategy_cls(), config=config)
