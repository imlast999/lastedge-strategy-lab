"""
XAUUSD Asian-London Strategy - London Open Liquidity & Session Breakout
========================================================================
Estrategia cuantitativa de alta selectividad para Oro (XAU/USD).
Explota la anomalía microestructural de la apertura de Londres (07:00 a 12:00 UTC)
tras la fase de acumulación del rango asiático (01:00 a 06:00 UTC):

1. Mide la acumulación del rango asiático (Asian High / Asian Low / Range).
2. Filtra la normalidad de la compresión (rango no excesivo ni insignificante).
3. Detecta dos modos operativos complementarios:
   - Modo Expansión (Breakout): Ruptura direccional a favor de la tendencia macro (EMA200/EMA50) con momentum RSI.
   - Modo Barrido (Liquidity Sweep): Falsa ruptura de rango con mecha de rechazo y cierre de vuelta dentro del rango.
4. Gestión de riesgo asimétrica institucional (R:R 1:1.5 a 1:2.0).
5. Filtro de sesión: Solo busca entradas entre las 07:00 y las 12:00 UTC.
"""

from typing import Dict, Optional, Any, Union
import pandas as pd
import numpy as np
import logging
from datetime import datetime

from strategies.base import BaseStrategy, StrategyMetadata, SignalIntent

logger = logging.getLogger(__name__)


class XAUUSDAsianLondonStrategy(BaseStrategy):
    """
    Estrategia de Liquidez y Ruptura de Sesión Asiática/Londres para Oro (XAU/USD).
    """

    def __init__(self):
        super().__init__("XAUUSD_Asian_London")
        self.strategy_name = "xauusd_asian_london"

    @property
    def metadata(self) -> StrategyMetadata:
        return StrategyMetadata(
            required_history=200,
            symbol="XAUUSD",
            timeframe="H1",
            strategy_name=self.strategy_name,
            version="1.0",
        )

    def _get_default_config(self) -> Dict[str, Any]:
        return {
            # Horarios de sesión (UTC)
            "asia_start_hour": 1,
            "asia_end_hour": 6,
            "london_start_hour": 7,
            "london_end_hour": 12,

            # Filtros de rango asiático relativo al ATR
            "min_asia_range_atr": 0.35,
            "max_asia_range_atr": 3.20,

            # Indicadores de tendencia y momentum
            "ema_fast": 20,
            "ema_medium": 50,
            "ema_macro": 200,
            "atr_period": 14,
            "rsi_period": 14,
            "rsi_bull_min": 50.0,
            "rsi_bear_max": 50.0,

            # Gestión de riesgo (R:R asimétrico)
            "sl_atr_mult": 1.50,
            "tp_risk_mult": 1.75,   # TP = Entry +- (Risk * 1.75) -> R:R 1:1.75
            "min_rejection_wick_pct": 0.25,

            # Identificación
            "symbol": "XAUUSD",
            "timeframe": "H1",
        }

    def _add_specific_indicators(self, df: pd.DataFrame, config: Dict[str, Any]) -> pd.DataFrame:
        """Añade los indicadores específicos de la estrategia (EMA200, etc.)."""
        cfg = {**self._get_default_config(), **(config or {})}
        df["ema200"] = self._ema(df["close"], int(cfg.get("ema_macro", 200)))
        return df

    def detect_setup(self, df: pd.DataFrame, config: Optional[Dict[str, Any]] = None) -> Optional[Union[Dict[str, Any], SignalIntent]]:
        """
        Detecta si la vela actual en la ventana de Londres cumple los criterios
        de Ruptura de Sesión Asiática o Barrido de Liquidez institucional.
        """
        cfg = {**self._get_default_config(), **(config or {})}
        if len(df) < self.metadata.required_history:
            return None

        # Verificar timestamps y sesión horaria
        if "time" not in df.columns:
            return None

        last_row = df.iloc[-1]
        last_dt = pd.to_datetime(last_row["time"])
        current_hour = last_dt.hour

        # Solo buscamos entradas en la ventana operativa de Londres
        if current_hour < cfg["london_start_hour"] or current_hour > cfg["london_end_hour"]:
            return None

        # Asegurar indicadores calculados
        if "ema200" not in df.columns or "atr" not in df.columns or "rsi" not in df.columns:
            df = self.add_indicators(df, cfg)
            last_row = df.iloc[-1]

        atr = float(last_row["atr"])
        if np.isnan(atr) or atr <= 0:
            return None

        price = float(last_row["close"])
        open_price = float(last_row["open"])
        high_price = float(last_row["high"])
        low_price = float(last_row["low"])
        ema50 = float(last_row["ema50"])
        ema200 = float(last_row["ema200"])
        rsi = float(last_row["rsi"])

        # Identificar las velas de la sesión asiática del mismo día calendario
        df_times = pd.to_datetime(df["time"])
        current_date = last_dt.date()
        same_day_mask = df_times.dt.date == current_date
        asia_mask = same_day_mask & (df_times.dt.hour >= cfg["asia_start_hour"]) & (df_times.dt.hour <= cfg["asia_end_hour"])
        asia_candles = df[asia_mask]

        # Requerimos al menos 3 velas para calcular un rango asiático representativo
        if len(asia_candles) < 3:
            return None

        asia_high = float(asia_candles["high"].max())
        asia_low = float(asia_candles["low"].min())
        asia_range = asia_high - asia_low

        # Filtro de normalidad del rango asiático
        if asia_range < (cfg["min_asia_range_atr"] * atr) or asia_range > (cfg["max_asia_range_atr"] * atr):
            return None

        # Filtros de tendencia macro
        bullish_macro = (price > ema200) and (ema50 > ema200 * 0.997)
        bearish_macro = (price < ema200) and (ema50 < ema200 * 1.003)

        candle_range = max(high_price - low_price, 1e-4)
        lower_wick_pct = (min(open_price, price) - low_price) / candle_range
        upper_wick_pct = (high_price - max(open_price, price)) / candle_range

        # =====================================================================
        # ESCENARIO 1: COMPRA (BUY)
        # =====================================================================
        # Modo A: Ruptura alcista con expansión sobre el rango asiático
        breakout_buy = (price > asia_high) and (price > open_price) and (rsi >= cfg["rsi_bull_min"]) and bullish_macro

        # Modo B: Barrido de liquidez bajo el mínimo asiático con rechazo alcista
        sweep_buy = (low_price < asia_low) and (price > asia_low) and (lower_wick_pct >= cfg["min_rejection_wick_pct"]) and (rsi >= 40.0) and bullish_macro

        if breakout_buy or sweep_buy:
            setup_type = "BREAKOUT" if breakout_buy else "LIQUIDITY_SWEEP"
            sl_distance = cfg["sl_atr_mult"] * atr
            sl_price = round(price - sl_distance, 2)
            tp_distance = sl_distance * cfg["tp_risk_mult"]
            tp_price = round(price + tp_distance, 2)

            return {
                "type": "BUY",
                "entry": round(price, 2),
                "sl": sl_price,
                "tp": tp_price,
                "confidence": "HIGH" if breakout_buy and rsi > 58 else "MEDIUM",
                "explanation": f"XAUUSD Asian-London Buy ({setup_type}): Expansión alcista en sesión Londres sobre nivel {asia_high:.2f} (RSI: {rsi:.1f}, ATR: {atr:.2f}).",
                "context": {
                    "strategy": self.strategy_name,
                    "symbol": "XAUUSD",
                    "setup_mode": setup_type,
                    "asia_high": asia_high,
                    "asia_low": asia_low,
                    "asia_range": asia_range,
                    "atr": atr,
                    "rsi": rsi,
                    "rr": cfg["tp_risk_mult"],
                }
            }

        # =====================================================================
        # ESCENARIO 2: VENTA (SELL)
        # =====================================================================
        # Modo A: Ruptura bajista con expansión bajo el rango asiático
        breakout_sell = (price < asia_low) and (price < open_price) and (rsi <= cfg["rsi_bear_max"]) and bearish_macro

        # Modo B: Barrido de liquidez sobre el máximo asiático con rechazo bajista
        sweep_sell = (high_price > asia_high) and (price < asia_high) and (upper_wick_pct >= cfg["min_rejection_wick_pct"]) and (rsi <= 60.0) and bearish_macro

        if breakout_sell or sweep_sell:
            setup_type = "BREAKOUT" if breakout_sell else "LIQUIDITY_SWEEP"
            sl_distance = cfg["sl_atr_mult"] * atr
            sl_price = round(price + sl_distance, 2)
            tp_distance = sl_distance * cfg["tp_risk_mult"]
            tp_price = round(price - tp_distance, 2)

            return {
                "type": "SELL",
                "entry": round(price, 2),
                "sl": sl_price,
                "tp": tp_price,
                "confidence": "HIGH" if breakout_sell and rsi < 42 else "MEDIUM",
                "explanation": f"XAUUSD Asian-London Sell ({setup_type}): Expansión bajista en sesión Londres bajo nivel {asia_low:.2f} (RSI: {rsi:.1f}, ATR: {atr:.2f}).",
                "context": {
                    "strategy": self.strategy_name,
                    "symbol": "XAUUSD",
                    "setup_mode": setup_type,
                    "asia_high": asia_high,
                    "asia_low": asia_low,
                    "asia_range": asia_range,
                    "atr": atr,
                    "rsi": rsi,
                    "rr": cfg["tp_risk_mult"],
                }
            }

        return None
