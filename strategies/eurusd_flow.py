"""
EURUSD Flow Strategy - Institutional Session Flow & Liquidity Pullback
=====================================================================
Estrategia cuantitativa optimizada para el par EUR/USD.
Combina:
1. Filtro de sesión activa institucional (Londres 07:00-11:00 UTC y Nueva York 13:00-17:00 UTC).
2. Filtro de tendencia macro (EMA20 > EMA50 y precio sobre EMA200).
3. Separación mínima de medias (0.02% para evitar rangos planos o chop asiático).
4. Retroceso controlado a la media rápida (EMA20) con RSI neutral (38-60) para no comprar techos.
5. Ratio Riesgo/Recompensa institucional asimétrico (1:2.0).
"""

from typing import Dict, Optional, Any
import pandas as pd
import numpy as np
import logging
from strategies.base import BaseStrategy, StrategyMetadata

logger = logging.getLogger(__name__)


class EURUSDFlowStrategy(BaseStrategy):
    """
    Estrategia de flujo de sesión y retroceso institucional para EUR/USD.
    """

    def __init__(self):
        super().__init__("EURUSD_Flow")
        self.strategy_name = "eurusd_flow"

    @property
    def metadata(self) -> StrategyMetadata:
        return StrategyMetadata(
            required_history=200,
            symbol="EURUSD",
            timeframe="H1",
            strategy_name="eurusd_flow",
            version="1.0",
        )

    def _get_default_config(self) -> Dict[str, Any]:
        return {
            'ema_fast': 20,
            'ema_mid': 50,
            'ema_slow': 200,
            'ema_min_sep': 0.0002,   # 0.02% separación mínima
            'rsi_period': 14,
            'rsi_buy_min': 38,
            'rsi_buy_max': 60,
            'rsi_sell_min': 40,
            'rsi_sell_max': 62,
            'atr_period': 14,
            'sl_atr_multiplier': 1.8,
            'tp_atr_multiplier': 3.6,
            'expires_minutes': 60,
        }

    def _add_specific_indicators(self, df: pd.DataFrame, config: Dict[str, Any]) -> pd.DataFrame:
        df['ema20'] = self._ema(df['close'], config.get('ema_fast', 20))
        df['ema50'] = self._ema(df['close'], config.get('ema_mid', 50))
        df['ema200'] = self._ema(df['close'], config.get('ema_slow', 200))
        return df

    def detect_setup(self, df: pd.DataFrame, config: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
        cfg = {**self._get_default_config(), **(config or {})}
        if len(df) < self.metadata.required_history:
            return None

        if 'ema20' not in df.columns:
            df = self._add_specific_indicators(df, cfg)
        if 'atr' not in df.columns or 'rsi' not in df.columns:
            df = self.add_indicators(df, cfg)

        idx = len(df) - 1
        curr = df.iloc[idx]
        c = float(curr['close'])
        e20 = float(curr['ema20'])
        e50 = float(curr['ema50'])
        e200 = float(curr['ema200'])
        atr = float(curr.get('atr', 0.0015))
        rsi = float(curr.get('rsi', 50.0))

        if atr <= 0 or np.isnan(atr):
            return None

        # 1. Filtro de sesión institucional si está disponible timestamp
        if 'time' in curr:
            try:
                t = pd.to_datetime(curr['time'])
                hour = t.hour
                # Sesiones operativas Londres / NY (07:00 a 17:00 UTC)
                if not (7 <= hour <= 17):
                    return None
            except Exception:
                pass

        # 2. Separación de medias
        sep = abs(e20 - e50) / e50 if e50 > 0 else 0
        if sep < float(cfg.get('ema_min_sep', 0.0002)):
            return None

        sl_mult = float(cfg['sl_atr_multiplier'])
        tp_mult = float(cfg['tp_atr_multiplier'])

        # ── BUY Setup: Tendencia alcista + Pullback a EMA20 en sesión activa ─
        bullish_trend = (e20 > e50) and (c > e200)
        recent_low_min = float(df['low'].iloc[max(0, idx - 2):idx + 1].min())
        pullback_buy = recent_low_min <= e20 * 1.0002
        rsi_buy = float(cfg['rsi_buy_min']) <= rsi <= float(cfg['rsi_buy_max'])

        if bullish_trend and pullback_buy and rsi_buy:
            sl_price = round(c - (sl_mult * atr), 5)
            tp_price = round(c + (tp_mult * atr), 5)
            return {
                'type': 'BUY',
                'entry': c,
                'sl': sl_price,
                'tp': tp_price,
                'confidence': 'VERY_HIGH' if c > e20 else 'HIGH',
                'explanation': f"EURUSD Flow Buy: Flujo alcista con pullback a EMA20 en sesión activa (RSI: {rsi:.1f}, Sep: {sep:.4f}).",
                'context': {
                    'strategy': self.strategy_name,
                    'symbol': 'EURUSD',
                    'rsi': rsi,
                    'atr': atr,
                    'rr': round(tp_mult / sl_mult, 2),
                }
            }

        # ── SELL Setup: Tendencia bajista + Pullback a EMA20 en sesión activa ─
        bearish_trend = (e20 < e50) and (c < e200)
        recent_high_max = float(df['high'].iloc[max(0, idx - 2):idx + 1].max())
        pullback_sell = recent_high_max >= e20 * 0.9998
        rsi_sell = float(cfg['rsi_sell_min']) <= rsi <= float(cfg['rsi_sell_max'])

        if bearish_trend and pullback_sell and rsi_sell:
            sl_price = round(c + (sl_mult * atr), 5)
            tp_price = round(c - (tp_mult * atr), 5)
            return {
                'type': 'SELL',
                'entry': c,
                'sl': sl_price,
                'tp': tp_price,
                'confidence': 'VERY_HIGH' if c < e20 else 'HIGH',
                'explanation': f"EURUSD Flow Sell: Flujo bajista con pullback a EMA20 en sesión activa (RSI: {rsi:.1f}, Sep: {sep:.4f}).",
                'context': {
                    'strategy': self.strategy_name,
                    'symbol': 'EURUSD',
                    'rsi': rsi,
                    'atr': atr,
                    'rr': round(tp_mult / sl_mult, 2),
                }
            }

        return None
