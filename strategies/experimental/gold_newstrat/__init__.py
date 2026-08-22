"""
GSRS (Gold Session Reversal Strategy) Package
=============================================
Contiene la especificación de investigación, esqueleto ejecutable y la
clase de estrategia XAUUSDGSRSStrategy integrada con BaseStrategy de LastEdge.
"""

from .gsrs_strategy import (
    GSRSConfig,
    GSRSState,
    GSRSStrategy,
    XAUUSDGSRSStrategy,
    Candle,
    SwingPoint,
    TradeSetup,
)

__all__ = [
    "GSRSConfig",
    "GSRSState",
    "GSRSStrategy",
    "XAUUSDGSRSStrategy",
    "Candle",
    "SwingPoint",
    "TradeSetup",
]
