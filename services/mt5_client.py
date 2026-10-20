"""
LastEdge Strategy Lab — MetaTrader 5 Historical Data Client
services/mt5_client.py

Permite a los servicios de investigación cuantitativa y backtesting descargar
velas históricas de alta fidelidad directamente desde el terminal MetaTrader 5.
"""

from __future__ import annotations

import os
import time
import logging
from typing import Optional, Union
import pandas as pd
from dotenv import load_dotenv

logger = logging.getLogger(__name__)

_MT5_INITIALIZED = False


def initialize(retries: int = 3, backoff_factor: float = 2.0, initial_delay: float = 1.0) -> bool:
    """
    Inicializa la conexión con el terminal MetaTrader 5 local.
    """
    global _MT5_INITIALIZED
    if _MT5_INITIALIZED:
        return True

    try:
        import MetaTrader5 as mt5
    except ImportError:
        logger.warning("[MT5Client] Paquete MetaTrader5 no instalado en el entorno.")
        return False

    load_dotenv()

    login_id_str = os.getenv("MT5_LOGIN")
    password = os.getenv("MT5_PASSWORD")
    server = os.getenv("MT5_SERVER")
    path = os.getenv("MT5_PATH")

    if password and password.startswith('"') and password.endswith('"'):
        password = password[1:-1]
    if server and server.startswith('"') and server.endswith('"'):
        server = server[1:-1]

    kwargs = {}
    if path:
        kwargs["path"] = path
    if login_id_str and password and server:
        try:
            kwargs["login"] = int(login_id_str)
            kwargs["password"] = password
            kwargs["server"] = server
        except ValueError:
            pass

    attempt = 0
    while attempt < retries:
        try:
            ok = mt5.initialize(**kwargs)
            if ok:
                _MT5_INITIALIZED = True
                logger.info("[MT5Client] MetaTrader 5 inicializado con éxito para Strategy Lab.")
                return True
            err = mt5.last_error()
            logger.warning("[MT5Client] Error al inicializar MT5: %s", err)
        except Exception as e:
            logger.exception("[MT5Client] Excepción durante inicialización de MT5: %s", e)

        attempt += 1
        if attempt < retries:
            time.sleep(initial_delay * (backoff_factor ** (attempt - 1)))

    return False


def shutdown() -> None:
    """Cierra la conexión con MT5."""
    global _MT5_INITIALIZED
    try:
        import MetaTrader5 as mt5
        mt5.shutdown()
        _MT5_INITIALIZED = False
    except Exception:
        pass


def get_candles(symbol: str, timeframe: Union[str, int], n: int = 20000) -> Optional[pd.DataFrame]:
    """
    Descarga las últimas `n` velas históricas para `symbol` y `timeframe`.
    """
    try:
        import MetaTrader5 as mt5
    except ImportError:
        return None

    if not initialize():
        return None

    sym = symbol.upper()
    si = mt5.symbol_info(sym)
    if si is None:
        try:
            syms = mt5.symbols_get()
            if syms:
                matches = [s.name for s in syms if sym.lower() in s.name.lower()]
                if matches:
                    sym = matches[0]
                    si = mt5.symbol_info(sym)
        except Exception:
            pass

    if si is None:
        logger.warning("[MT5Client] Símbolo '%s' no disponible en MT5.", symbol)
        return None

    if not si.visible:
        try:
            mt5.symbol_select(sym, True)
        except Exception:
            pass

    tf_map = {
        "M1": mt5.TIMEFRAME_M1,
        "M5": mt5.TIMEFRAME_M5,
        "M15": mt5.TIMEFRAME_M15,
        "M30": mt5.TIMEFRAME_M30,
        "H1": mt5.TIMEFRAME_H1,
        "H4": mt5.TIMEFRAME_H4,
        "D1": mt5.TIMEFRAME_D1,
    }
    mt5_tf = tf_map.get(str(timeframe).upper(), mt5.TIMEFRAME_H1) if isinstance(timeframe, str) else timeframe

    for attempt in range(3):
        rates = mt5.copy_rates_from_pos(sym, mt5_tf, 0, n)
        if rates is not None and len(rates) > 0:
            df = pd.DataFrame(rates)
            df["time"] = pd.to_datetime(df["time"], unit="s", utc=True)
            df.attrs["symbol"] = sym
            df["symbol"] = sym
            return df
        time.sleep(0.5 * (attempt + 1))

    return None
