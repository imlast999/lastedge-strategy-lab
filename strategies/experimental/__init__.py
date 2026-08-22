# Estrategias experimentales — no usar en producción
# Descartadas tras optimización (grid search, mayo 2026) o en proceso de validación en laboratorio

from .gold_newstrat import XAUUSDGSRSStrategy, GSRSStrategy, GSRSConfig

__all__ = ["XAUUSDGSRSStrategy", "GSRSStrategy", "GSRSConfig"]
