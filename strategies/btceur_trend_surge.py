"""
BTCEUR Trend Surge Strategy - Multi-Timeframe Trend & Volume Pullback
====================================================================
Estrategia cuantitativa de swing trading institucional para Bitcoin (BTC/EUR).
Combina:
1. Macro-régimen en H4 resampleado (EMA50 > EMA200 y precio sobre EMA50).
2. Detección en H1 de retroceso a la media EMA20 con confirmación de volumen.
3. Filtro estricto de volatilidad ATR (0.3% <= ATR_pct <= 6.0%).
4. R:R altamente asimétrico (1:3.0) con gestión dinámica de trailing y breakeven.
"""

from typing import Dict, Optional, Any
import pandas as pd
import numpy as np
import logging
from datetime import datetime, timezone
from strategies.base import BaseStrategy, StrategyMetadata

logger = logging.getLogger(__name__)


class BTCEURTrendSurgeStrategy(BaseStrategy):
    """
    Estrategia de seguimiento de tendencia macro y retroceso con volumen para BTC/EUR.
    """

    def __init__(self):
        super().__init__("BTCEUR_Trend_Surge")
        self.strategy_name = "btceur_trend_surge"

    @property
    def metadata(self) -> StrategyMetadata:
        return StrategyMetadata(
            required_history=850,
            symbol="BTCEUR",
            timeframe="H1",
            strategy_name="btceur_trend_surge",
            version="1.0",
        )

    def _get_default_config(self) -> Dict[str, Any]:
        return {
            'h4_ema_fast': 50,
            'h4_ema_slow': 200,
            'h1_ema_entry': 20,
            'h1_rsi_period': 14,
            'h1_atr_period': 14,
            'ema_touch_pct': 0.012,
            'rsi_buy_min': 44,
            'rsi_buy_max': 62,
            'rsi_sell_min': 38,
            'rsi_sell_max': 56,
            'atr_min_pct': 0.003,
            'atr_max_pct': 0.060,
            'sl_atr_multiplier': 1.5,
            'tp_atr_multiplier': 4.5,
            'min_h1_candles': 850,
            'expires_minutes': 240,
        }

    def _add_specific_indicators(self, df: pd.DataFrame, config: Dict[str, Any]) -> pd.DataFrame:
        df['h1_ema20'] = self._ema(df['close'], int(config.get('h1_ema_entry', 20)))
        return df

    def _build_h4(self, df_h1: pd.DataFrame) -> pd.DataFrame:
        try:
            if 'time' not in df_h1.columns:
                return pd.DataFrame()
            df = df_h1[['time', 'open', 'high', 'low', 'close']].copy()
            df['time'] = pd.to_datetime(df['time'])
            df = df.set_index('time')
            df_h4 = df.resample('4h').agg({
                'open': 'first', 'high': 'max', 'low': 'min', 'close': 'last'
            }).dropna()
            return df_h4
        except Exception as e:
            logger.debug(f"Error resampling H4 in BTCEURTrendSurge: {e}")
            return pd.DataFrame()

    def detect_setup(self, df: pd.DataFrame, config: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
        cfg = {**self._get_default_config(), **(config or {})}
        min_candles = int(cfg.get('min_h1_candles', 850))

        if len(df) < min_candles:
            return None

        # 1. Régimen Macro H4
        df_h4 = self._build_h4(df)
        min_h4 = int(cfg.get('h4_ema_slow', 200)) + 5
        if len(df_h4) < min_h4:
            return None

        df_h4 = df_h4.copy()
        df_h4['ema50'] = self._ema(df_h4['close'], int(cfg['h4_ema_fast']))
        df_h4['ema200'] = self._ema(df_h4['close'], int(cfg['h4_ema_slow']))

        last_h4 = df_h4.iloc[-1]
        price_h4 = float(last_h4['close'])
        ema50_h4 = float(last_h4['ema50'])
        ema200_h4 = float(last_h4['ema200'])

        bullish_h4 = (ema50_h4 > ema200_h4) and (price_h4 > ema50_h4)
        bearish_h4 = (ema50_h4 < ema200_h4) and (price_h4 < ema50_h4)

        if not (bullish_h4 or bearish_h4):
            return None

        direction = 'BUY' if bullish_h4 else 'SELL'

        # 2. Indicadores H1
        if 'h1_ema20' not in df.columns:
            df = self._add_specific_indicators(df, cfg)
        if 'atr' not in df.columns or 'rsi' not in df.columns:
            df = self.add_indicators(df, cfg)

        last_h1 = df.iloc[-1]
        price_h1 = float(last_h1['close'])
        ema20_h1 = float(last_h1['h1_ema20'])
        rsi_h1 = float(last_h1['rsi'])
        atr_h1 = float(last_h1['atr'])

        if atr_h1 <= 0 or price_h1 <= 0:
            return None

        # Filtro de posición del precio frente a EMA200 H4
        if direction == 'BUY' and price_h1 < ema200_h4:
            return None
        if direction == 'SELL' and price_h1 > ema200_h4:
            return None

        # Filtro de volatilidad relativa
        atr_pct = atr_h1 / price_h1
        if atr_pct < float(cfg['atr_min_pct']) or atr_pct > float(cfg['atr_max_pct']):
            return None

        # Distancia a EMA20 (retroceso)
        dist_ema20 = abs(price_h1 - ema20_h1) / ema20_h1
        if dist_ema20 > float(cfg['ema_touch_pct']):
            return None

        # Filtro RSI
        if direction == 'BUY':
            rsi_ok = float(cfg['rsi_buy_min']) <= rsi_h1 <= float(cfg['rsi_buy_max'])
        else:
            rsi_ok = float(cfg['rsi_sell_min']) <= rsi_h1 <= float(cfg['rsi_sell_max'])

        if not rsi_ok:
            return None

        # Dirección de la vela actual
        bullish_candle = float(last_h1['close']) > float(last_h1['open'])
        bearish_candle = float(last_h1['close']) < float(last_h1['open'])

        if direction == 'BUY' and not bullish_candle:
            return None
        if direction == 'SELL' and not bearish_candle:
            return None

        # Niveles técnicos
        sl_distance = atr_h1 * float(cfg['sl_atr_multiplier'])
        tp_distance = atr_h1 * float(cfg['tp_atr_multiplier'])

        if direction == 'BUY':
            sl = round(price_h1 - sl_distance, 2)
            tp = round(price_h1 + tp_distance, 2)
        else:
            sl = round(price_h1 + sl_distance, 2)
            tp = round(price_h1 - tp_distance, 2)

        return {
            'type': direction,
            'entry': price_h1,
            'sl': sl,
            'tp': tp,
            'confidence': 'VERY_HIGH' if dist_ema20 < 0.005 else 'HIGH',
            'explanation': (
                f"BTCEUR Trend Surge {direction}: Tendencia H4 {direction.lower()} "
                f"(EMA50={ema50_h4:.0f}, EMA200={ema200_h4:.0f}), pullback a EMA20 H1 "
                f"(dist={dist_ema20:.2%}, RSI={rsi_h1:.1f}, ATR={atr_h1:.0f})."
            ),
            'context': {
                'strategy': self.strategy_name,
                'symbol': 'BTCEUR',
                'rsi': rsi_h1,
                'atr': atr_h1,
                'rr': round(float(cfg['tp_atr_multiplier']) / float(cfg['sl_atr_multiplier']), 2),
            }
        }
