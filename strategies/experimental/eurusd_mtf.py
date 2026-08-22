"""
EURUSD Multi-Timeframe Trend Following Strategy

Estrategia de swing trading basada en:
- D1: Tendencia principal (EMA50 > EMA200, RSI filtro)
- H4: Entrada en retroceso a EMA50

Filosofía: pocas operaciones (2-6/mes), alta calidad, capturar tendencias largas.

Los datos de entrada son H4. El D1 se obtiene resampleando internamente,
lo que permite usar el replay engine existente sin modificaciones.
"""

from typing import Dict, Optional
import pandas as pd
import numpy as np
from datetime import datetime, timezone, timedelta
import logging

from ..base import BaseStrategy

logger = logging.getLogger(__name__)


class EURUSDMultiTimeframeStrategy(BaseStrategy):
    """
    Trend Following D1+H4 para EURUSD.

    Condiciones de entrada:
    BUY:
      - D1: EMA50 > EMA200 AND close > EMA50
      - D1: RSI(14) > 55
      - H4: precio toca EMA50 (distancia ≤ ema_touch_pct)
      - H4: última vela cierra alcista

    SELL:
      - D1: EMA50 < EMA200 AND close < EMA50
      - D1: RSI(14) < 45
      - H4: precio toca EMA50
      - H4: última vela cierra bajista

    SL: ATR(D1) * sl_atr_multiplier
    TP: ATR(D1) * tp_atr_multiplier  (o trailing stop en producción)
    """

    def __init__(self):
        super().__init__("EURUSD_MTF")

    def _get_default_config(self) -> Dict:
        return {
            # D1 indicadores
            'd1_ema_fast':  50,
            'd1_ema_slow':  200,
            'd1_rsi_period': 14,
            'd1_rsi_buy':   55,    # RSI mínimo para BUY
            'd1_rsi_sell':  45,    # RSI máximo para SELL

            # H4 entrada
            'h4_ema_period':   50,
            'ema_touch_pct':   0.0015,  # 0.15% distancia máxima a EMA50 H4

            # Gestión de riesgo
            'sl_atr_multiplier': 2.5,   # SL amplio para swing — aguanta retrocesos D1
            'tp_atr_multiplier': 5.0,   # R:R 2.0 con SL 2.5x
            'expires_minutes':   240,   # 4h (una vela H4)

            # Filtros de seguridad
            'max_spread_pips':  3.0,
            'min_atr_d1_pips':  30.0,   # ATR D1 mínimo (mercado con volatilidad)
        }

    def _add_specific_indicators(self, df: pd.DataFrame, config: Dict) -> pd.DataFrame:
        """
        Añade indicadores H4. Los indicadores D1 se calculan en detect_setup
        resampleando el DataFrame H4.
        """
        df['h4_ema50'] = self._ema(df['close'], config['h4_ema_period'])
        return df

    def _resample_to_d1(self, df_h4: pd.DataFrame) -> pd.DataFrame:
        """
        Convierte datos H4 a D1 resampleando.
        Requiere columna 'time' en el DataFrame.
        """
        try:
            df = df_h4.copy()

            # Asegurar que 'time' es datetime
            if 'time' not in df.columns:
                # Sin columna time, no podemos resamplear — usar aproximación
                # Cada 6 velas H4 = 1 vela D1
                return self._approximate_d1(df)

            df['time'] = pd.to_datetime(df['time'])
            df = df.set_index('time')

            d1 = df.resample('D').agg({
                'open':  'first',
                'high':  'max',
                'low':   'min',
                'close': 'last',
            }).dropna()

            d1 = d1.reset_index()
            return d1

        except Exception as e:
            logger.debug(f"[MTF] Error resampleando a D1: {e}, usando aproximación")
            return self._approximate_d1(df_h4)

    def _approximate_d1(self, df_h4: pd.DataFrame) -> pd.DataFrame:
        """
        Aproximación D1 agrupando cada 6 velas H4 (6 * 4h = 24h).
        Usado cuando no hay columna 'time'.
        """
        n = 6  # velas H4 por día
        rows = []
        for i in range(0, len(df_h4) - n, n):
            chunk = df_h4.iloc[i:i + n]
            rows.append({
                'open':  float(chunk.iloc[0]['open']),
                'high':  float(chunk['high'].max()),
                'low':   float(chunk['low'].min()),
                'close': float(chunk.iloc[-1]['close']),
            })
        return pd.DataFrame(rows)

    def _add_d1_indicators(self, df_d1: pd.DataFrame, config: Dict) -> pd.DataFrame:
        """Calcula EMA50, EMA200, RSI y ATR sobre datos D1."""
        df_d1 = df_d1.copy()
        df_d1['ema50']  = self._ema(df_d1['close'], config['d1_ema_fast'])
        df_d1['ema200'] = self._ema(df_d1['close'], config['d1_ema_slow'])
        df_d1['rsi']    = self._rsi(df_d1['close'], config['d1_rsi_period'])
        df_d1['atr']    = self._atr(df_d1, 14)
        return df_d1

    def detect_setup(self, df: pd.DataFrame, config: Dict = None) -> Optional[Dict]:
        """
        Detecta setup multi-timeframe D1+H4.

        df debe contener datos H4 con al menos 300 velas
        (suficiente para EMA200 D1 ≈ 200 días * 6 velas/día = 1200 H4,
        pero en práctica con 300 H4 ≈ 50 días D1 ya tenemos señal).
        """
        cfg = {**self.default_config, **(config or {})}

        # Necesitamos suficientes velas H4 para calcular EMA200 en D1
        # 200 días D1 * 6 velas H4/día = 1200 H4 mínimo ideal
        # Usamos 250 como mínimo práctico (≈ 42 días D1)
        min_bars = max(250, cfg['d1_ema_slow'] * 2)
        if not self.validate_data(df) or len(df) < min_bars:
            logger.debug("[MTF][REJECT] insufficient_data | len=%d min=%d", len(df), min_bars)
            return None

        # ── Calcular indicadores H4 ───────────────────────────────────────────
        df = self.add_indicators(df, cfg)
        last_h4  = df.iloc[-1]
        price    = float(last_h4['close'])
        h4_ema50 = float(last_h4['h4_ema50'])

        # ── Construir D1 y calcular indicadores ──────────────────────────────
        df_d1 = self._resample_to_d1(df)

        if len(df_d1) < cfg['d1_ema_slow']:
            logger.debug("[MTF][REJECT] insufficient_d1_bars | d1_len=%d needed=%d",
                        len(df_d1), cfg['d1_ema_slow'])
            return None

        df_d1 = self._add_d1_indicators(df_d1, cfg)
        last_d1 = df_d1.iloc[-1]

        d1_ema50  = float(last_d1['ema50'])
        d1_ema200 = float(last_d1['ema200'])
        d1_rsi    = float(last_d1['rsi'])
        d1_atr    = float(last_d1['atr'])

        # ── Filtro de seguridad: ATR D1 mínimo ───────────────────────────────
        d1_atr_pips = d1_atr / 0.0001
        if d1_atr_pips < cfg['min_atr_d1_pips']:
            logger.debug("[MTF][REJECT] low_volatility | atr_pips=%.1f min=%.1f",
                        d1_atr_pips, cfg['min_atr_d1_pips'])
            return None

        # ── CONDICIÓN 1: Tendencia D1 ─────────────────────────────────────────
        d1_bullish = d1_ema50 > d1_ema200 and float(last_d1['close']) > d1_ema50
        d1_bearish = d1_ema50 < d1_ema200 and float(last_d1['close']) < d1_ema50

        if not (d1_bullish or d1_bearish):
            logger.debug("[MTF][REJECT] no_d1_trend | ema50=%.5f ema200=%.5f close=%.5f",
                        d1_ema50, d1_ema200, float(last_d1['close']))
            return None

        direction = 'BUY' if d1_bullish else 'SELL'

        # ── CONDICIÓN 2: Filtro RSI D1 ────────────────────────────────────────
        if direction == 'BUY' and d1_rsi <= cfg['d1_rsi_buy']:
            logger.debug("[MTF][REJECT] rsi_too_low_for_buy | rsi=%.1f threshold=%.1f",
                        d1_rsi, cfg['d1_rsi_buy'])
            return None
        if direction == 'SELL' and d1_rsi >= cfg['d1_rsi_sell']:
            logger.debug("[MTF][REJECT] rsi_too_high_for_sell | rsi=%.1f threshold=%.1f",
                        d1_rsi, cfg['d1_rsi_sell'])
            return None

        # ── CONDICIÓN 3: Precio H4 toca EMA50 H4 (retroceso) ─────────────────
        dist_to_h4_ema50 = abs(price - h4_ema50) / h4_ema50
        if dist_to_h4_ema50 > cfg['ema_touch_pct']:
            logger.debug("[MTF][REJECT] price_far_from_h4_ema50 | dist=%.4f max=%.4f",
                        dist_to_h4_ema50, cfg['ema_touch_pct'])
            return None

        # ── CONDICIÓN 4: Última vela H4 en dirección correcta ────────────────
        h4_bullish_candle = float(last_h4['close']) > float(last_h4['open'])
        h4_bearish_candle = float(last_h4['close']) < float(last_h4['open'])

        if direction == 'BUY' and not h4_bullish_candle:
            logger.debug("[MTF][REJECT] h4_candle_not_bullish")
            return None
        if direction == 'SELL' and not h4_bearish_candle:
            logger.debug("[MTF][REJECT] h4_candle_not_bearish")
            return None

        # ── NIVELES (basados en ATR D1) ───────────────────────────────────────
        sl_distance = d1_atr * cfg['sl_atr_multiplier']
        tp_distance = d1_atr * cfg['tp_atr_multiplier']

        if direction == 'BUY':
            sl = price - sl_distance
            tp = price + tp_distance
        else:
            sl = price + sl_distance
            tp = price - tp_distance

        rr = tp_distance / sl_distance if sl_distance > 0 else 0

        # ── FORTALEZA ─────────────────────────────────────────────────────────
        # Qué tan lejos está RSI del umbral (más lejos = más momentum)
        rsi_strength = abs(d1_rsi - 50) / 50
        # Qué tan separadas están las EMAs D1
        ema_sep = abs(d1_ema50 - d1_ema200) / d1_ema200
        ema_strength = min(1.0, ema_sep * 100)

        setup_strength = (rsi_strength * 0.4) + (ema_strength * 0.4) + (0.2 if rr >= 2.0 else 0.1)

        # ── SEÑAL ─────────────────────────────────────────────────────────────
        signal = {
            'type': direction,
            'entry': price,
            'sl': sl,
            'tp': tp,
            'timeframe': 'H4',
            'explanation': (
                f'EURUSD MTF: {direction} | '
                f'D1 EMA50{">" if d1_bullish else "<"}EMA200 | '
                f'RSI D1={d1_rsi:.1f} | '
                f'H4 retroceso EMA50 | '
                f'R:R={rr:.1f}'
            ),
            'expires': datetime.now(timezone.utc) + timedelta(minutes=cfg['expires_minutes']),
            'setup_strength': setup_strength,
            'context': {
                'strategy': 'eurusd_mtf',
                'confirmations': [
                    {'name': 'D1_TREND',    'passed': True,  'value': 1.0, 'description': f'D1 tendencia {direction}'},
                    {'name': 'D1_RSI',      'passed': True,  'value': d1_rsi, 'description': f'RSI D1={d1_rsi:.1f}'},
                    {'name': 'H4_PULLBACK', 'passed': True,  'value': dist_to_h4_ema50, 'description': f'Retroceso H4 EMA50'},
                    {'name': 'H4_CANDLE',   'passed': True,  'value': 1.0, 'description': f'Vela H4 {direction}'},
                ],
                'market_conditions': {
                    'd1_ema50':   d1_ema50,
                    'd1_ema200':  d1_ema200,
                    'd1_rsi':     d1_rsi,
                    'd1_atr':     d1_atr,
                    'd1_atr_pips': d1_atr_pips,
                    'h4_ema50':   h4_ema50,
                    'dist_to_h4_ema50': dist_to_h4_ema50,
                    'ema_separation': ema_sep,
                },
                'risk_reward': rr,
                'mtf_strategy': True,
            }
        }

        logger.info(
            "[MTF][SIGNAL] type=%s | price=%.5f | D1_RSI=%.1f | D1_EMA_sep=%.4f | H4_dist=%.4f | RR=%.1f",
            direction, price, d1_rsi, ema_sep, dist_to_h4_ema50, rr
        )

        return signal
