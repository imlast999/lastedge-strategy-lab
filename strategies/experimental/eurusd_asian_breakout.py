"""
EURUSD Asian Range Breakout Strategy  (eurusd_asian_breakout)

Estrategia de breakout del rango asiático optimizada para sesión de Londres.

Lógica:
  1. Calcular rango asiático (00:00–06:00 UTC) desde datos H1
  2. Durante sesión de Londres (07:00–11:00 UTC):
     - BUY  si precio cierra > asia_high + buffer
     - SELL si precio cierra < asia_low  - buffer
  3. SL en el extremo opuesto del rango asiático
  4. TP = entry ± range_size × tp_multiplier

Filtros:
  - range_size mínimo (evita días sin movimiento)
  - No operar viernes
  - Solo 1 señal por día

Datos de entrada: H1 (el M15 se aproxima con H1 para compatibilidad con el replay engine).
Lookback mínimo: 50 velas H1 (≈ 2 días).
"""

import logging
from typing import Dict, Optional
import pandas as pd
import numpy as np
from datetime import datetime, timezone, timedelta

from ..base import BaseStrategy

logger = logging.getLogger(__name__)


class EURUSDAsianBreakoutStrategy(BaseStrategy):

    def __init__(self):
        super().__init__("EURUSD_AsianBreakout")
        # Registro de última señal por día (evita duplicados intradiarios)
        self._last_signal_date: Optional[str] = None

    def reset_state(self) -> None:
        """Resetea estado interno — llamar entre ventanas de walk-forward / optimización."""
        self._last_signal_date = None

    def _get_default_config(self) -> Dict:
        return {
            # Sesiones (horas UTC)
            'asia_start':   0,
            'asia_end':     6,
            'london_start': 7,
            'london_end':   11,

            # Breakout
            'buffer':       0.0003,   # 3 pips por encima/debajo del rango

            # Filtros
            'min_range_pips':  4.0,   # rango mínimo en pips (optimizado)
            'max_range_pips':  80.0,  # rango máximo (evita días muy volátiles)

            # Gestión
            'tp_multiplier':   1.5,   # TP = range × 1.5 (optimizado backtest 3k)
            'sl_buffer':       0.0001, # buffer adicional en SL

            # Mínimo de velas H1
            'min_h1_candles':  50,
            'expires_minutes': 240,   # 4h (fin de sesión Londres)
        }

    def _add_specific_indicators(self, df: pd.DataFrame, config: Dict) -> pd.DataFrame:
        return df  # No necesita indicadores adicionales

    def _get_asian_range(self, df: pd.DataFrame, cfg: Dict) -> Optional[Dict]:
        """
        Calcula el rango asiático del día más reciente con datos completos.
        Requiere columna 'time' en el DataFrame.
        """
        if 'time' not in df.columns:
            return None

        try:
            df = df.copy()
            df['time'] = pd.to_datetime(df['time'])
            df['hour'] = df['time'].dt.hour
            df['date'] = df['time'].dt.date

            # Obtener el día de la última vela
            last_date = df['date'].iloc[-1]

            # Velas asiáticas del día actual
            asian = df[
                (df['date'] == last_date) &
                (df['hour'] >= cfg['asia_start']) &
                (df['hour'] < cfg['asia_end'])
            ]

            # Si no hay suficientes velas asiáticas hoy, usar el día anterior
            if len(asian) < 3:
                dates = sorted(df['date'].unique())
                if len(dates) < 2:
                    return None
                prev_date = dates[-2]
                asian = df[
                    (df['date'] == prev_date) &
                    (df['hour'] >= cfg['asia_start']) &
                    (df['hour'] < cfg['asia_end'])
                ]

            if len(asian) < 3:
                return None

            asia_high = float(asian['high'].max())
            asia_low  = float(asian['low'].min())
            range_size = asia_high - asia_low
            range_pips = range_size / 0.0001

            return {
                'high':       asia_high,
                'low':        asia_low,
                'range_size': range_size,
                'range_pips': range_pips,
                'date':       str(last_date),
            }

        except Exception as e:
            logger.debug("[ASIAN_BO] Error calculando rango: %s", e)
            return None

    def detect_setup(self, df: pd.DataFrame, config: Dict = None) -> Optional[Dict]:
        cfg = {**self.default_config, **(config or {})}

        if not self.validate_data(df) or len(df) < cfg['min_h1_candles']:
            return None

        if 'time' not in df.columns:
            logger.debug("[ASIAN_BO][REJECT] no_time_column")
            return None

        df = df.copy()
        df['time'] = pd.to_datetime(df['time'])

        last = df.iloc[-1]
        current_hour = last['time'].hour
        current_date = str(last['time'].date())
        weekday = last['time'].weekday()  # 4 = viernes

        # ── Filtro: no operar viernes ─────────────────────────────────────────
        if weekday == 4:
            logger.debug("[ASIAN_BO][REJECT] friday")
            return None

        # ── Filtro: solo durante sesión de Londres ────────────────────────────
        if not (cfg['london_start'] <= current_hour < cfg['london_end']):
            logger.debug("[ASIAN_BO][REJECT] outside_london | hour=%d", current_hour)
            return None

        # ── Filtro: solo 1 señal por día ──────────────────────────────────────
        if self._last_signal_date == current_date:
            logger.debug("[ASIAN_BO][REJECT] already_signaled_today | date=%s", current_date)
            return None

        # ── Calcular rango asiático ───────────────────────────────────────────
        asian = self._get_asian_range(df, cfg)
        if asian is None:
            logger.debug("[ASIAN_BO][REJECT] no_asian_range")
            return None

        range_pips = asian['range_pips']

        # ── Filtro: rango mínimo y máximo ─────────────────────────────────────
        if range_pips < cfg['min_range_pips']:
            logger.debug("[ASIAN_BO][REJECT] range_too_small | pips=%.1f", range_pips)
            return None
        if range_pips > cfg['max_range_pips']:
            logger.debug("[ASIAN_BO][REJECT] range_too_large | pips=%.1f", range_pips)
            return None

        price = float(last['close'])
        asia_high = asian['high']
        asia_low  = asian['low']
        range_size = asian['range_size']

        # ── Condición de breakout ─────────────────────────────────────────────
        buy_level  = asia_high + cfg['buffer']
        sell_level = asia_low  - cfg['buffer']

        if price > buy_level:
            direction = 'BUY'
        elif price < sell_level:
            direction = 'SELL'
        else:
            logger.debug("[ASIAN_BO][REJECT] no_breakout | price=%.5f high=%.5f low=%.5f",
                        price, buy_level, sell_level)
            return None

        # ── Niveles ───────────────────────────────────────────────────────────
        tp_distance = range_size * cfg['tp_multiplier']

        if direction == 'BUY':
            sl = asia_low - cfg['sl_buffer']
            tp = price + tp_distance
        else:
            sl = asia_high + cfg['sl_buffer']
            tp = price - tp_distance

        sl_distance = abs(price - sl)
        rr = tp_distance / sl_distance if sl_distance > 0 else 0

        # ── Fortaleza ─────────────────────────────────────────────────────────
        # Rango más grande = setup más claro
        range_strength = min(1.0, range_pips / 30.0)
        strength = range_strength

        # Registrar señal del día
        self._last_signal_date = current_date

        logger.info(
            "[ASIAN_BO][SIGNAL] %s | price=%.5f | range=%.1fpips | "
            "high=%.5f low=%.5f | R:R=%.1f",
            direction, price, range_pips, asia_high, asia_low, rr
        )

        return {
            'type': direction,
            'entry': price,
            'sl': sl,
            'tp': tp,
            'timeframe': 'H1',
            'explanation': (
                f'EURUSD Asian Breakout: {direction} | '
                f'Rango asiático {range_pips:.1f} pips | '
                f'Breakout {"alcista" if direction=="BUY" else "bajista"} | R:R={rr:.1f}'
            ),
            'expires': datetime.now(timezone.utc) + timedelta(minutes=cfg['expires_minutes']),
            'setup_strength': strength,
            'context': {
                'strategy': 'eurusd_asian_breakout',
                'confirmations': [
                    {'name': 'LONDON_SESSION', 'passed': True, 'value': current_hour,
                     'description': f'Hora Londres: {current_hour}:00'},
                    {'name': 'ASIAN_RANGE',    'passed': True, 'value': range_pips,
                     'description': f'Rango: {range_pips:.1f} pips'},
                    {'name': 'BREAKOUT',       'passed': True, 'value': price,
                     'description': f'Breakout {">" if direction=="BUY" else "<"} {buy_level if direction=="BUY" else sell_level:.5f}'},
                ],
                'market_conditions': {
                    'asia_high':   asia_high,
                    'asia_low':    asia_low,
                    'range_pips':  range_pips,
                    'range_size':  range_size,
                    'buy_level':   buy_level,
                    'sell_level':  sell_level,
                    'london_hour': current_hour,
                },
                'risk_reward': rr,
                'asian_breakout': True,
            }
        }
