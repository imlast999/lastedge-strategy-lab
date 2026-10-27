"""
XAUUSD Surge Strategy - Volatility Squeeze & Institutional Breakout
==================================================================
Estrategia cuantitativa de alta selectividad diseñada para Oro (XAU/USD).
Resuelve el problema de whipsaw de los cruces simples de medias móviles:
1. Detecta compresión de volatilidad (Bollinger Bands dentro de Keltner Channel).
2. Captura la expansión explosiva cuando el precio quiebra el rango Donchian de 20 periodos.
3. Filtra la dirección mediante la media institucional EMA100/EMA200 y momentum RSI.
4. R:R institucional asimétrico (1:2.33).
"""

from typing import Dict, Optional, Any
import pandas as pd
import numpy as np
import logging
from strategies.base import BaseStrategy, StrategyMetadata

logger = logging.getLogger(__name__)


class XAUUSDSurgeStrategy(BaseStrategy):
    """
    Estrategia de ruptura de compresión de volatilidad para Oro (XAU/USD).
    """

    def __init__(self):
        super().__init__("XAUUSD_Surge")
        self.strategy_name = "xauusd_surge"

    @property
    def metadata(self) -> StrategyMetadata:
        return StrategyMetadata(
            required_history=200,
            symbol="XAUUSD",
            timeframe="H1",
            strategy_name="xauusd_surge",
            version="1.0",
        )

    def _get_default_config(self) -> Dict[str, Any]:
        return {
            'bb_period': 20,
            'bb_std': 2.0,
            'kc_mult': 1.5,
            'donchian_period': 20,
            'ema_trend': 100,
            'rsi_period': 14,
            'rsi_buy': 54,
            'rsi_sell': 46,
            'atr_period': 14,
            'sl_atr_multiplier': 1.8,
            'tp_atr_multiplier': 4.2,
            'squeeze_lookback': 5,
            'expires_minutes': 60,
        }

    def _add_specific_indicators(self, df: pd.DataFrame, config: Dict[str, Any]) -> pd.DataFrame:
        p = int(config.get('bb_period', 20))
        std_dev = float(config.get('bb_std', 2.0))
        kc_mult = float(config.get('kc_mult', 1.5))
        d_p = int(config.get('donchian_period', 20))

        df['ema100'] = self._ema(df['close'], int(config.get('ema_trend', 100)))
        df['sma20'] = df['close'].rolling(p).mean()
        df['bb_std_val'] = df['close'].rolling(p).std()
        df['bb_upper'] = df['sma20'] + (std_dev * df['bb_std_val'])
        df['bb_lower'] = df['sma20'] - (std_dev * df['bb_std_val'])

        # Keltner Channel
        if 'atr' not in df.columns:
            df['atr'] = self._atr(df, int(config.get('atr_period', 14)))
        df['kc_upper'] = df['sma20'] + (kc_mult * df['atr'])
        df['kc_lower'] = df['sma20'] - (kc_mult * df['atr'])

        # Squeeze indicator
        df['squeeze'] = (df['bb_upper'] <= df['kc_upper']) & (df['bb_lower'] >= df['kc_lower'])

        # Donchian Channels
        df['donchian_high'] = df['high'].rolling(d_p).max()
        df['donchian_low'] = df['low'].rolling(d_p).min()

        return df

    def detect_setup(self, df: pd.DataFrame, config: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
        cfg = {**self._get_default_config(), **(config or {})}
        if len(df) < self.metadata.required_history:
            return None

        if 'bb_upper' not in df.columns or 'donchian_high' not in df.columns:
            df = self._add_specific_indicators(df, cfg)
        if 'rsi' not in df.columns or 'atr' not in df.columns:
            df = self.add_indicators(df, cfg)

        idx = len(df) - 1
        curr = df.iloc[idx]
        prev = df.iloc[idx - 1]

        c = float(curr['close'])
        prev_c = float(prev['close'])
        e100 = float(curr['ema100'])
        atr = float(curr.get('atr', 5.0))
        rsi = float(curr.get('rsi', 50.0))

        if atr <= 0 or np.isnan(atr):
            return None

        sq_lookback = int(cfg.get('squeeze_lookback', 5))
        recent_squeezes = df['squeeze'].iloc[max(0, idx - sq_lookback):idx].values
        had_squeeze = bool(np.any(recent_squeezes))

        donchian_high_prev = float(df['donchian_high'].iloc[idx - 1])
        donchian_low_prev = float(df['donchian_low'].iloc[idx - 1])

        sl_mult = float(cfg['sl_atr_multiplier'])
        tp_mult = float(cfg['tp_atr_multiplier'])

        # ── 1. BUY: Ruptura alcista tras compresión ─────────────────────────
        buy_breakout = (prev_c <= donchian_high_prev) and (c > donchian_high_prev)
        trend_buy = c > e100
        rsi_buy = rsi >= float(cfg['rsi_buy'])

        if had_squeeze and buy_breakout and trend_buy and rsi_buy:
            sl_price = round(c - (sl_mult * atr), 2)
            tp_price = round(c + (tp_mult * atr), 2)
            return {
                'type': 'BUY',
                'entry': c,
                'sl': sl_price,
                'tp': tp_price,
                'confidence': 'VERY_HIGH' if rsi > 60 else 'HIGH',
                'explanation': f"XAUUSD Surge Buy: Ruptura de compresión Donchian alcista sobre EMA100 (RSI: {rsi:.1f}, Squeeze: Activo).",
                'context': {
                    'strategy': self.strategy_name,
                    'symbol': 'XAUUSD',
                    'rsi': rsi,
                    'atr': atr,
                    'rr': round(tp_mult / sl_mult, 2),
                }
            }

        # ── 2. SELL: Ruptura bajista tras compresión ────────────────────────
        sell_breakout = (prev_c >= donchian_low_prev) and (c < donchian_low_prev)
        trend_sell = c < e100
        rsi_sell = rsi <= float(cfg['rsi_sell'])

        if had_squeeze and sell_breakout and trend_sell and rsi_sell:
            sl_price = round(c + (sl_mult * atr), 2)
            tp_price = round(c - (tp_mult * atr), 2)
            return {
                'type': 'SELL',
                'entry': c,
                'sl': sl_price,
                'tp': tp_price,
                'confidence': 'VERY_HIGH' if rsi < 40 else 'HIGH',
                'explanation': f"XAUUSD Surge Sell: Ruptura de compresión Donchian bajista bajo EMA100 (RSI: {rsi:.1f}, Squeeze: Activo).",
                'context': {
                    'strategy': self.strategy_name,
                    'symbol': 'XAUUSD',
                    'rsi': rsi,
                    'atr': atr,
                    'rr': round(tp_mult / sl_mult, 2),
                }
            }

        return None
