"""
XAUUSD Psychological Levels Reversal Strategy  (xauusd_psychological)

Estrategia de reversión en niveles psicológicos del oro.

Lógica:
  1. Detectar cuando el precio se acerca a un múltiplo de $100 (o $50)
  2. Buscar rechazo: mecha larga + RSI extremo
  3. Entrada tras vela de confirmación en dirección opuesta

Niveles: 4700, 4800, 4900, 5000... (adaptado al precio actual del broker ~4800)
         También niveles intermedios: 4750, 4850...

Datos de entrada: H1.
Lookback mínimo: 30 velas H1.
"""

import logging
from typing import Dict, List, Optional
import pandas as pd
import numpy as np
from datetime import datetime, timezone, timedelta

from ..base import BaseStrategy

logger = logging.getLogger(__name__)


class XAUUSDPsychologicalStrategy(BaseStrategy):

    def __init__(self):
        super().__init__("XAUUSD_Psychological")

    def _get_default_config(self) -> Dict:
        return {
            # Niveles psicológicos
            'level_step':       100.0,   # múltiplos de $100
            'use_half_levels':  True,    # también $50 intermedios
            'proximity_pct':    0.003,   # 0.3% de distancia al nivel

            # Confirmación de rechazo
            'wick_ratio_min':   0.40,    # mecha debe ser ≥ 40% del rango total
            'rsi_overbought':   65,      # RSI para SELL (más permisivo que 70)
            'rsi_oversold':     35,      # RSI para BUY  (más permisivo que 30)

            # Filtros
            'atr_max_multiplier': 2.5,   # no operar si ATR > 2.5× media (muy volátil)

            # Gestión
            'sl_buffer':        2.0,     # USD más allá del nivel
            'tp1_multiplier':   1.0,     # TP1 = 1R
            'tp_multiplier':    2.0,     # TP final = 2R

            'min_h1_candles':   30,
            'expires_minutes':  240,
        }

    def _add_specific_indicators(self, df: pd.DataFrame, config: Dict) -> pd.DataFrame:
        return df

    def _get_nearby_levels(self, price: float, cfg: Dict) -> List[float]:
        """Devuelve los niveles psicológicos cercanos al precio."""
        step = cfg['level_step']
        base = round(price / step) * step

        levels = [base - step, base, base + step]

        if cfg['use_half_levels']:
            half = step / 2
            levels += [base - half, base + half]

        return sorted(levels)

    def _nearest_level(self, price: float, cfg: Dict) -> Optional[float]:
        """Devuelve el nivel psicológico más cercano si está dentro del rango de proximidad."""
        levels = self._get_nearby_levels(price, cfg)
        proximity = price * cfg['proximity_pct']

        closest = min(levels, key=lambda l: abs(price - l))
        if abs(price - closest) <= proximity:
            return closest
        return None

    def _has_rejection_wick(self, candle: pd.Series, direction: str, cfg: Dict) -> bool:
        """
        Verifica si la vela tiene una mecha de rechazo significativa.
        direction='SELL' → mecha superior larga (rechazo desde arriba)
        direction='BUY'  → mecha inferior larga (rechazo desde abajo)
        """
        total_range = float(candle['high']) - float(candle['low'])
        if total_range <= 0:
            return False

        body_top    = max(float(candle['open']), float(candle['close']))
        body_bottom = min(float(candle['open']), float(candle['close']))

        if direction == 'SELL':
            upper_wick = float(candle['high']) - body_top
            return (upper_wick / total_range) >= cfg['wick_ratio_min']
        else:
            lower_wick = body_bottom - float(candle['low'])
            return (lower_wick / total_range) >= cfg['wick_ratio_min']

    def detect_setup(self, df: pd.DataFrame, config: Dict = None) -> Optional[Dict]:
        cfg = {**self.default_config, **(config or {})}

        if not self.validate_data(df) or len(df) < cfg['min_h1_candles']:
            return None

        df = self.add_indicators(df, cfg)

        last = df.iloc[-1]
        prev = df.iloc[-2]

        price = float(last['close'])
        rsi   = float(last['rsi'])
        atr   = float(last['atr'])

        # ── Filtro de volatilidad ─────────────────────────────────────────────
        atr_mean = df['atr'].tail(20).mean()
        if atr > atr_mean * cfg['atr_max_multiplier']:
            logger.debug("[PSYCH][REJECT] atr_too_high | atr=%.1f mean=%.1f", atr, atr_mean)
            return None

        # ── Nivel psicológico cercano ─────────────────────────────────────────
        level = self._nearest_level(price, cfg)
        if level is None:
            logger.debug("[PSYCH][REJECT] no_nearby_level | price=%.2f", price)
            return None

        # ── Determinar dirección por RSI ──────────────────────────────────────
        if rsi > cfg['rsi_overbought']:
            direction = 'SELL'
        elif rsi < cfg['rsi_oversold']:
            direction = 'BUY'
        else:
            logger.debug("[PSYCH][REJECT] rsi_neutral | rsi=%.1f", rsi)
            return None

        # ── Verificar mecha de rechazo en la vela anterior ───────────────────
        # Usamos la vela anterior porque la actual puede no estar cerrada
        if not self._has_rejection_wick(prev, direction, cfg):
            logger.debug("[PSYCH][REJECT] no_rejection_wick | dir=%s", direction)
            return None

        # ── Confirmación: vela actual en dirección correcta ───────────────────
        if direction == 'SELL' and float(last['close']) >= float(last['open']):
            logger.debug("[PSYCH][REJECT] confirmation_candle_not_bearish")
            return None
        if direction == 'BUY' and float(last['close']) <= float(last['open']):
            logger.debug("[PSYCH][REJECT] confirmation_candle_not_bullish")
            return None

        # ── Niveles (SL/TP del lado correcto respecto al entry) ───────────────
        buf = cfg['sl_buffer']
        if direction == 'SELL':
            sl = max(level + buf, price + buf)
            sl_distance = sl - price
            if sl_distance <= 0:
                return None
            tp = price - sl_distance * cfg['tp_multiplier']
        else:
            sl = min(level - buf, price - buf)
            sl_distance = price - sl
            if sl_distance <= 0:
                return None
            tp = price + sl_distance * cfg['tp_multiplier']

        tp_distance = abs(tp - price)
        rr = tp_distance / sl_distance if sl_distance > 0 else 0

        # ── Fortaleza ─────────────────────────────────────────────────────────
        rsi_extreme = abs(rsi - 50) / 50
        proximity   = 1.0 - (abs(price - level) / (price * cfg['proximity_pct']))
        strength    = (rsi_extreme * 0.5) + (max(0, proximity) * 0.5)

        logger.info(
            "[PSYCH][SIGNAL] %s | price=%.2f | level=%.0f | rsi=%.1f | R:R=%.1f",
            direction, price, level, rsi, rr
        )

        return {
            'type': direction,
            'entry': price,
            'sl': sl,
            'tp': tp,
            'timeframe': 'H1',
            'explanation': (
                f'XAUUSD Psychological: {direction} | '
                f'Nivel ${level:.0f} | RSI={rsi:.0f} | '
                f'Rechazo {"superior" if direction=="SELL" else "inferior"} | R:R={rr:.1f}'
            ),
            'expires': datetime.now(timezone.utc) + timedelta(minutes=cfg['expires_minutes']),
            'setup_strength': strength,
            'context': {
                'strategy': 'xauusd_psychological',
                'confirmations': [
                    {'name': 'PSYCH_LEVEL',  'passed': True, 'value': level,
                     'description': f'Nivel psicológico: ${level:.0f}'},
                    {'name': 'RSI_EXTREME',  'passed': True, 'value': rsi,
                     'description': f'RSI extremo: {rsi:.1f}'},
                    {'name': 'WICK_REJECT',  'passed': True, 'value': 1.0,
                     'description': f'Mecha de rechazo {direction}'},
                    {'name': 'CONFIRM_CANDLE','passed': True, 'value': 1.0,
                     'description': f'Vela confirmación {direction}'},
                ],
                'market_conditions': {
                    'level':      level,
                    'rsi':        rsi,
                    'atr':        atr,
                    'atr_mean':   atr_mean,
                    'proximity':  abs(price - level),
                },
                'risk_reward': rr,
                'psychological_level': True,
            }
        }
