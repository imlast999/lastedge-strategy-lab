"""
Exit Research — Variantes de salida (símbolo-agnósticas).

La ENTRADA es idéntica para todas: la estrategia base detecta el setup.
Solo cambia cómo se calculan SL, TP y la simulación de cierre.

Cada variante implementa:
    compute_levels(entry, direction, atr, df_window) -> (sl, tp)
    simulate_exit(signal, df_full, start_index) -> (result, exit_price, profit_pips)

Pip size:
    Por defecto EURUSD (0.0001). El runner inyecta el pip_size correcto
    para cada símbolo llamando a set_pip_size() antes de ejecutar.
"""

from __future__ import annotations
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional, Tuple, Dict
import pandas as pd
import numpy as np
import logging

logger = logging.getLogger(__name__)

PIP_SIZE_EURUSD  = 0.0001
SPREAD_PIPS      = 1.2   # spread promedio EURUSD (de trade_costs.py)
COMMISSION_PIPS  = 0.3   # comisión round-trip a 0.1 lotes
ROUND_TRIP_COST  = 1.5   # spread 1.2 + commission 0.3 pips

# ── Tabla de pip size por símbolo ─────────────────────────────────────────────
# EURUSD/GBPUSD: 0.0001  (5-decimal brokers: 0.00001 — aquí usamos 0.0001)
# XAUUSD: 0.01  (1 pip = $0.01; ATR en H1 ≈ 2–5 USD ≈ 200–500 pips)
# BTCEUR: 1.0   (1 pip = 1 EUR)
_PIP_SIZE_BY_SYMBOL: Dict[str, float] = {
    "EURUSD": 0.0001,
    "GBPUSD": 0.0001,
    "USDJPY": 0.01,
    "XAUUSD": 0.01,
    "BTCEUR": 1.0,
    "BTCUSD": 1.0,
}


def get_pip_size(symbol: str) -> float:
    """
    Devuelve el tamaño de pip para el símbolo dado.
    Fallback: 0.0001 (estándar forex de 4 decimales).
    """
    return _PIP_SIZE_BY_SYMBOL.get(symbol.upper(), PIP_SIZE_EURUSD)


@dataclass
class ExitResult:
    result:      str            # 'WIN' | 'LOSS' | 'PENDING'
    exit_price:  Optional[float]
    exit_bar:    Optional[int]
    profit_pips: float
    mae_pips:    float = 0.0    # Maximum Adverse Excursion (pips en contra)
    mfe_pips:    float = 0.0    # Maximum Favorable Excursion (pips a favor)


def _net_pips(raw_pips: float) -> float:
    """Deduct fixed round-trip cost from any trade outcome."""
    return raw_pips - ROUND_TRIP_COST


def _calc_mae_mfe(
    direction: str,
    entry: float,
    df_full: pd.DataFrame,
    start_index: int,
    end_index: int,
    pip_size: float = PIP_SIZE_EURUSD,
) -> tuple[float, float]:
    """
    Calcula MAE (Maximum Adverse Excursion) y MFE (Maximum Favorable Excursion)
    en pips para un trade entre start_index y end_index (exclusive).

    MAE: mayor movimiento en contra visto antes del cierre.
    MFE: mayor movimiento a favor visto antes del cierre.

    Ambos se devuelven como valores positivos.
    pip_size: tamaño del pip del símbolo (default EURUSD=0.0001).
    """
    mae = 0.0
    mfe = 0.0
    for k in range(start_index + 1, min(end_index + 1, len(df_full))):
        high  = float(df_full.iloc[k]["high"])
        low   = float(df_full.iloc[k]["low"])
        if direction == "BUY":
            adverse   = (entry - low)  / pip_size
            favorable = (high - entry) / pip_size
        else:
            adverse   = (high - entry) / pip_size
            favorable = (entry - low)  / pip_size
        if adverse  > mae: mae = adverse
        if favorable > mfe: mfe = favorable
    return max(0.0, mae), max(0.0, mfe)


# ── Clase base ────────────────────────────────────────────────────────────────

class ExitVariant(ABC):
    """Interfaz común para todas las variantes de salida."""

    name: str        # identificador único
    label: str       # nombre legible para informes
    max_forward: int = 250  # máximo de velas a mirar hacia adelante

    # Pip size inyectado por el runner según el símbolo. Default: EURUSD.
    pip_size: float = PIP_SIZE_EURUSD

    def set_pip_size(self, size: float) -> None:
        """Inyecta el pip size correcto para el símbolo en análisis."""
        self.pip_size = size

    @abstractmethod
    def compute_levels(
        self,
        entry: float,
        direction: str,
        atr: float,
        df_window: pd.DataFrame,
    ) -> Tuple[float, Optional[float]]:
        """
        Devuelve (sl, tp).
        tp puede ser None si la variante usa trailing (se gestiona en simulate_exit).
        """
        ...

    def simulate_exit(
        self,
        entry: float,
        sl: float,
        tp: Optional[float],
        direction: str,
        df_full: pd.DataFrame,
        start_index: int,
        atr_at_entry: float,
    ) -> ExitResult:
        """
        Simula el cierre del trade vela a vela.
        La implementación por defecto usa TP/SL fijos.
        Las variantes con trailing sobreescriben este método.
        """
        ps = self.pip_size
        exit_bar = None
        for i in range(start_index + 1, min(start_index + self.max_forward, len(df_full))):
            high = float(df_full.iloc[i]["high"])
            low  = float(df_full.iloc[i]["low"])

            if direction == "BUY":
                if tp is not None and high >= tp:
                    raw = (tp - entry) / ps
                    exit_bar = i
                    mae, mfe = _calc_mae_mfe(direction, entry, df_full, start_index, i, ps)
                    return ExitResult("WIN", tp, i, _net_pips(raw), mae, mfe)
                if low <= sl:
                    raw = (sl - entry) / ps
                    exit_bar = i
                    mae, mfe = _calc_mae_mfe(direction, entry, df_full, start_index, i, ps)
                    return ExitResult("LOSS", sl, i, _net_pips(raw), mae, mfe)
            else:  # SELL
                if tp is not None and low <= tp:
                    raw = (entry - tp) / ps
                    exit_bar = i
                    mae, mfe = _calc_mae_mfe(direction, entry, df_full, start_index, i, ps)
                    return ExitResult("WIN", tp, i, _net_pips(raw), mae, mfe)
                if high >= sl:
                    raw = (entry - sl) / ps
                    exit_bar = i
                    mae, mfe = _calc_mae_mfe(direction, entry, df_full, start_index, i, ps)
                    return ExitResult("LOSS", sl, i, _net_pips(raw), mae, mfe)

        return ExitResult("PENDING", None, None, 0.0, 0.0, 0.0)


# ── Helper ────────────────────────────────────────────────────────────────────

def _fixed_rr(sl_mult: float, tp_mult: float, label: str, name_id: str) -> type:
    """Factory que genera clases de variante RR fijo."""
    _label = label   # capture before class body shadows the name

    class _Variant(ExitVariant):
        name  = name_id
        label = _label

        def compute_levels(self, entry, direction, atr, df_window):
            sl_dist = atr * sl_mult
            tp_dist = atr * tp_mult
            if direction == "BUY":
                return entry - sl_dist, entry + tp_dist
            return entry + sl_dist, entry - tp_dist

    _Variant.__name__ = f"Variant_{name_id}"
    return _Variant


# ══════════════════════════════════════════════════════════════════════════════
# VARIANTES 1–5: RR FIJOS (SL=1.5×ATR, TP variable)
# ══════════════════════════════════════════════════════════════════════════════

class Variant_RR2(_fixed_rr(1.5, 3.0, "RR 1:2 (SL=1.5, TP=3.0)", "rr_1_2")): pass
class Variant_RR25(_fixed_rr(1.5, 3.75, "RR 1:2.5 (SL=1.5, TP=3.75)", "rr_1_25")): pass
class Variant_RR3(_fixed_rr(1.5, 4.5, "RR 1:3 (SL=1.5, TP=4.5)", "rr_1_3")): pass
class Variant_RR35(_fixed_rr(1.5, 5.25, "RR 1:3.5 (SL=1.5, TP=5.25)", "rr_1_35")): pass
class Variant_RR4(_fixed_rr(1.5, 6.0, "RR 1:4 (actual) (SL=1.5, TP=6.0)", "rr_1_4")): pass


# ══════════════════════════════════════════════════════════════════════════════
# VARIANTE 6: Sin TP — solo Stop + Trailing ATR
# ══════════════════════════════════════════════════════════════════════════════

class Variant_TrailingATR(ExitVariant):
    """
    Sin TP fijo. El SL se arrastra con el precio usando un multiplicador ATR.
    SL inicial = 1.5×ATR desde entrada.
    Trailing: cada vez que el precio mejora 0.5×ATR se ajusta el SL
    para proteger al menos 0.5×ATR de beneficio.
    """
    name  = "trailing_atr"
    label = "Trailing ATR (sin TP fijo)"

    ATR_TRAIL_MULT = 1.5   # distancia de arrastre
    ATR_INIT_MULT  = 1.5   # SL inicial

    def compute_levels(self, entry, direction, atr, df_window):
        sl_dist = atr * self.ATR_INIT_MULT
        sl = entry - sl_dist if direction == "BUY" else entry + sl_dist
        return sl, None   # sin TP fijo

    def simulate_exit(self, entry, sl, tp, direction, df_full, start_index, atr_at_entry):
        ps = self.pip_size
        trail_dist = atr_at_entry * self.ATR_TRAIL_MULT
        current_sl = sl

        for i in range(start_index + 1, min(start_index + self.max_forward, len(df_full))):
            high = float(df_full.iloc[i]["high"])
            low  = float(df_full.iloc[i]["low"])
            close = float(df_full.iloc[i]["close"])

            if direction == "BUY":
                # Arrastrar SL hacia arriba
                new_sl = close - trail_dist
                if new_sl > current_sl:
                    current_sl = new_sl
                if low <= current_sl:
                    raw = (current_sl - entry) / ps
                    mae, mfe = _calc_mae_mfe(direction, entry, df_full, start_index, i, ps)
                    return ExitResult("WIN" if current_sl > entry else "LOSS",
                                      current_sl, i, _net_pips(raw), mae, mfe)
            else:
                # Arrastrar SL hacia abajo
                new_sl = close + trail_dist
                if new_sl < current_sl:
                    current_sl = new_sl
                if high >= current_sl:
                    raw = (entry - current_sl) / ps
                    mae, mfe = _calc_mae_mfe(direction, entry, df_full, start_index, i, ps)
                    return ExitResult("WIN" if current_sl < entry else "LOSS",
                                      current_sl, i, _net_pips(raw), mae, mfe)

        return ExitResult("PENDING", None, None, 0.0, 0.0, 0.0)


# ══════════════════════════════════════════════════════════════════════════════
# VARIANTE 7: Trailing EMA (el SL sigue la EMA20)
# ══════════════════════════════════════════════════════════════════════════════

class Variant_TrailingEMA(ExitVariant):
    """
    SL inicial = 1.5×ATR. Sin TP fijo.
    Mientras el trade está abierto, el SL se ajusta para seguir la EMA20
    (con un buffer de 0.5×ATR).
    """
    name  = "trailing_ema"
    label = "Trailing EMA20 (sin TP fijo)"

    ATR_INIT_MULT   = 1.5
    EMA_BUFFER_MULT = 0.5

    def compute_levels(self, entry, direction, atr, df_window):
        sl_dist = atr * self.ATR_INIT_MULT
        sl = entry - sl_dist if direction == "BUY" else entry + sl_dist
        return sl, None

    def simulate_exit(self, entry, sl, tp, direction, df_full, start_index, atr_at_entry):
        ps = self.pip_size
        current_sl = sl
        buffer = atr_at_entry * self.EMA_BUFFER_MULT

        for i in range(start_index + 1, min(start_index + self.max_forward, len(df_full))):
            high  = float(df_full.iloc[i]["high"])
            low   = float(df_full.iloc[i]["low"])
            ema20 = df_full["ema20"].iloc[i] if "ema20" in df_full.columns else None

            if ema20 is not None and not pd.isna(ema20):
                ema20 = float(ema20)
                if direction == "BUY":
                    candidate = ema20 - buffer
                    if candidate > current_sl:
                        current_sl = candidate
                else:
                    candidate = ema20 + buffer
                    if candidate < current_sl:
                        current_sl = candidate

            if direction == "BUY":
                if low <= current_sl:
                    raw = (current_sl - entry) / ps
                    mae, mfe = _calc_mae_mfe(direction, entry, df_full, start_index, i, ps)
                    return ExitResult("WIN" if current_sl > entry else "LOSS",
                                      current_sl, i, _net_pips(raw), mae, mfe)
            else:
                if high >= current_sl:
                    raw = (entry - current_sl) / ps
                    mae, mfe = _calc_mae_mfe(direction, entry, df_full, start_index, i, ps)
                    return ExitResult("WIN" if current_sl < entry else "LOSS",
                                      current_sl, i, _net_pips(raw), mae, mfe)

        return ExitResult("PENDING", None, None, 0.0, 0.0, 0.0)


# ══════════════════════════════════════════════════════════════════════════════
# VARIANTE 8: Trailing ATR Dinámico (recalcula ATR cada N velas)
# ══════════════════════════════════════════════════════════════════════════════

class Variant_DynamicATR(ExitVariant):
    """
    Similar a Trailing ATR pero recalcula el ATR cada 5 velas usando
    las últimas 14 velas disponibles, para adaptarse a cambios de volatilidad.
    """
    name  = "dynamic_atr"
    label = "Trailing ATR Dinámico"

    ATR_INIT_MULT  = 1.5
    ATR_TRAIL_MULT = 1.5
    RECALC_EVERY   = 5

    def compute_levels(self, entry, direction, atr, df_window):
        sl_dist = atr * self.ATR_INIT_MULT
        sl = entry - sl_dist if direction == "BUY" else entry + sl_dist
        return sl, None

    def simulate_exit(self, entry, sl, tp, direction, df_full, start_index, atr_at_entry):
        ps = self.pip_size
        current_sl = sl
        current_atr = atr_at_entry

        for i in range(start_index + 1, min(start_index + self.max_forward, len(df_full))):
            high  = float(df_full.iloc[i]["high"])
            low   = float(df_full.iloc[i]["low"])
            close = float(df_full.iloc[i]["close"])

            # Recalcular ATR periódicamente
            bars_in = i - start_index
            if bars_in % self.RECALC_EVERY == 0 and "atr" in df_full.columns:
                atr_val = df_full["atr"].iloc[i]
                if not pd.isna(atr_val) and atr_val > 0:
                    current_atr = float(atr_val)

            trail_dist = current_atr * self.ATR_TRAIL_MULT

            if direction == "BUY":
                new_sl = close - trail_dist
                if new_sl > current_sl:
                    current_sl = new_sl
                if low <= current_sl:
                    raw = (current_sl - entry) / ps
                    mae, mfe = _calc_mae_mfe(direction, entry, df_full, start_index, i, ps)
                    return ExitResult("WIN" if current_sl > entry else "LOSS",
                                      current_sl, i, _net_pips(raw), mae, mfe)
            else:
                new_sl = close + trail_dist
                if new_sl < current_sl:
                    current_sl = new_sl
                if high >= current_sl:
                    raw = (entry - current_sl) / ps
                    mae, mfe = _calc_mae_mfe(direction, entry, df_full, start_index, i, ps)
                    return ExitResult("WIN" if current_sl < entry else "LOSS",
                                      current_sl, i, _net_pips(raw), mae, mfe)

        return ExitResult("PENDING", None, None, 0.0, 0.0, 0.0)


# ══════════════════════════════════════════════════════════════════════════════
# VARIANTE 9: Break Even Automático (SL → entrada cuando precio llega a 1×ATR)
# ══════════════════════════════════════════════════════════════════════════════

class Variant_BreakEven(ExitVariant):
    """
    TP fijo = 4×ATR. SL inicial = 1.5×ATR.
    En cuanto el precio llega a 1×ATR de beneficio, el SL se mueve a
    entrada + pequeño buffer (break even).
    """
    name  = "break_even"
    label = "Break Even automático (TP=4×ATR)"

    ATR_SL_MULT = 1.5
    ATR_TP_MULT = 4.0
    ATR_BE_TRIGGER  = 1.0   # activar BE cuando precio llega a 1×ATR
    ATR_BE_BUFFER   = 0.1   # 0.1 pip en ATR sobre entrada

    def compute_levels(self, entry, direction, atr, df_window):
        sl = entry - atr * self.ATR_SL_MULT if direction == "BUY" else entry + atr * self.ATR_SL_MULT
        tp = entry + atr * self.ATR_TP_MULT if direction == "BUY" else entry - atr * self.ATR_TP_MULT
        return sl, tp

    def simulate_exit(self, entry, sl, tp, direction, df_full, start_index, atr_at_entry):
        ps = self.pip_size
        current_sl = sl
        be_triggered = False
        be_level = (entry + atr_at_entry * self.ATR_BE_BUFFER) if direction == "BUY" \
                   else (entry - atr_at_entry * self.ATR_BE_BUFFER)
        be_trigger_price = (entry + atr_at_entry * self.ATR_BE_TRIGGER) if direction == "BUY" \
                           else (entry - atr_at_entry * self.ATR_BE_TRIGGER)

        for i in range(start_index + 1, min(start_index + self.max_forward, len(df_full))):
            high  = float(df_full.iloc[i]["high"])
            low   = float(df_full.iloc[i]["low"])

            if direction == "BUY":
                if not be_triggered and high >= be_trigger_price:
                    current_sl = max(current_sl, be_level)
                    be_triggered = True
                if tp is not None and high >= tp:
                    raw = (tp - entry) / ps
                    mae, mfe = _calc_mae_mfe(direction, entry, df_full, start_index, i, ps)
                    return ExitResult("WIN", tp, i, _net_pips(raw), mae, mfe)
                if low <= current_sl:
                    raw = (current_sl - entry) / ps
                    res = "WIN" if current_sl >= be_level else "LOSS"
                    mae, mfe = _calc_mae_mfe(direction, entry, df_full, start_index, i, ps)
                    return ExitResult(res, current_sl, i, _net_pips(raw), mae, mfe)
            else:
                if not be_triggered and low <= be_trigger_price:
                    current_sl = min(current_sl, be_level)
                    be_triggered = True
                if tp is not None and low <= tp:
                    raw = (entry - tp) / ps
                    mae, mfe = _calc_mae_mfe(direction, entry, df_full, start_index, i, ps)
                    return ExitResult("WIN", tp, i, _net_pips(raw), mae, mfe)
                if high >= current_sl:
                    raw = (entry - current_sl) / ps
                    res = "WIN" if current_sl <= be_level else "LOSS"
                    mae, mfe = _calc_mae_mfe(direction, entry, df_full, start_index, i, ps)
                    return ExitResult(res, current_sl, i, _net_pips(raw), mae, mfe)

        return ExitResult("PENDING", None, None, 0.0, 0.0, 0.0)


# ══════════════════════════════════════════════════════════════════════════════
# VARIANTE 10: 50% parcial al 2×ATR + trailing del resto
# ══════════════════════════════════════════════════════════════════════════════

class Variant_PartialClose(ExitVariant):
    """
    Al llegar a 2×ATR de beneficio, cierra el 50% al precio de cierre de esa vela
    (primer ExitResult, result='WIN'). El 50% restante continúa con trailing SL
    = close ± 1.5×ATR y TP máximo = entry ± 5×ATR_entrada.

    simulate_exit devuelve list[ExitResult]:
    - Dos elementos si el cierre parcial se activa (primer leg parcial + segundo leg trailing).
    - Un elemento si el parcial nunca se activa (resultado completo de la posición).
    """
    name  = "partial_close"
    label = "50% Parcial + Trailing"

    ATR_SL_MULT      = 1.5
    ATR_PARTIAL_MULT = 2.0   # trigger del cierre parcial
    ATR_TRAIL_MULT   = 1.5   # trailing del 50% restante
    ATR_MAX_MULT     = 5.0   # TP máximo del 50% restante

    def compute_levels(self, entry, direction, atr, df_window):
        sl = entry - atr * self.ATR_SL_MULT if direction == "BUY" else entry + atr * self.ATR_SL_MULT
        tp = None  # gestionado en simulate_exit
        return sl, tp

    def simulate_exit(  # type: ignore[override]
        self,
        entry: float,
        sl: float,
        tp: Optional[float],
        direction: str,
        df_full: pd.DataFrame,
        start_index: int,
        atr_at_entry: float,
    ) -> list[ExitResult]:
        """
        Returns list[ExitResult]:
        - Two ExitResults when the 2×ATR partial close triggers:
            [0] WIN  — 50% closed at close price of the trigger bar
            [1] WIN|LOSS — remaining 50% closed by trailing SL or max TP
        - One ExitResult when partial never triggers (full position result).
        MAE/MFE are measured from entry to the respective exit bar.
        """
        ps = self.pip_size
        current_sl  = sl
        trail_dist  = atr_at_entry * self.ATR_TRAIL_MULT
        partial_trigger_price = (
            entry + atr_at_entry * self.ATR_PARTIAL_MULT
            if direction == "BUY"
            else entry - atr_at_entry * self.ATR_PARTIAL_MULT
        )
        max_tp = (
            entry + atr_at_entry * self.ATR_MAX_MULT
            if direction == "BUY"
            else entry - atr_at_entry * self.ATR_MAX_MULT
        )

        end_index = min(start_index + self.max_forward, len(df_full))

        # ── Phase 1: scan for partial-close trigger OR early SL hit ──────────
        for i in range(start_index + 1, end_index):
            high  = float(df_full.iloc[i]["high"])
            low   = float(df_full.iloc[i]["low"])
            close = float(df_full.iloc[i]["close"])

            if direction == "BUY":
                if low <= current_sl:
                    raw = (current_sl - entry) / ps
                    mae, mfe = _calc_mae_mfe(direction, entry, df_full, start_index, i, ps)
                    return [ExitResult("LOSS", current_sl, i, _net_pips(raw), mae, mfe)]

                if close >= partial_trigger_price:
                    partial_close_price = close
                    raw_partial = (partial_close_price - entry) / ps
                    mae1, mfe1 = _calc_mae_mfe(direction, entry, df_full, start_index, i, ps)
                    first_result = ExitResult(
                        "WIN", partial_close_price, i, _net_pips(raw_partial), mae1, mfe1,
                    )
                    current_sl = max(current_sl, entry)
                    partial_bar = i
                    break

            else:  # SELL
                if high >= current_sl:
                    raw = (entry - current_sl) / ps
                    mae, mfe = _calc_mae_mfe(direction, entry, df_full, start_index, i, ps)
                    return [ExitResult("LOSS", current_sl, i, _net_pips(raw), mae, mfe)]

                if close <= partial_trigger_price:
                    partial_close_price = close
                    raw_partial = (entry - partial_close_price) / ps
                    mae1, mfe1 = _calc_mae_mfe(direction, entry, df_full, start_index, i, ps)
                    first_result = ExitResult(
                        "WIN", partial_close_price, i, _net_pips(raw_partial), mae1, mfe1,
                    )
                    current_sl = min(current_sl, entry)
                    partial_bar = i
                    break

        else:
            return [ExitResult("PENDING", None, None, 0.0, 0.0, 0.0)]

        # ── Phase 2: simulate the remaining 50% with trailing SL ─────────────
        for j in range(partial_bar + 1, end_index):
            high  = float(df_full.iloc[j]["high"])
            low   = float(df_full.iloc[j]["low"])
            close = float(df_full.iloc[j]["close"])

            if direction == "BUY":
                new_sl = close - trail_dist
                if new_sl > current_sl:
                    current_sl = new_sl

                if high >= max_tp:
                    raw_rest = (max_tp - entry) / ps
                    mae2, mfe2 = _calc_mae_mfe(direction, entry, df_full, start_index, j, ps)
                    second_result = ExitResult("WIN", max_tp, j, _net_pips(raw_rest), mae2, mfe2)
                    return [first_result, second_result]

                if low <= current_sl:
                    raw_rest = (current_sl - entry) / ps
                    result = "WIN" if current_sl > entry else "LOSS"
                    mae2, mfe2 = _calc_mae_mfe(direction, entry, df_full, start_index, j, ps)
                    second_result = ExitResult(result, current_sl, j, _net_pips(raw_rest), mae2, mfe2)
                    return [first_result, second_result]

            else:  # SELL
                new_sl = close + trail_dist
                if new_sl < current_sl:
                    current_sl = new_sl

                if low <= max_tp:
                    raw_rest = (entry - max_tp) / ps
                    mae2, mfe2 = _calc_mae_mfe(direction, entry, df_full, start_index, j, ps)
                    second_result = ExitResult("WIN", max_tp, j, _net_pips(raw_rest), mae2, mfe2)
                    return [first_result, second_result]

                if high >= current_sl:
                    raw_rest = (entry - current_sl) / ps
                    result = "WIN" if current_sl < entry else "LOSS"
                    mae2, mfe2 = _calc_mae_mfe(direction, entry, df_full, start_index, j, ps)
                    second_result = ExitResult(result, current_sl, j, _net_pips(raw_rest), mae2, mfe2)
                    return [first_result, second_result]

        return [first_result, ExitResult("PENDING", None, None, 0.0, 0.0, 0.0)]


# ══════════════════════════════════════════════════════════════════════════════
# VARIANTE 11: Trailing Donchian Channel
# ══════════════════════════════════════════════════════════════════════════════

class Variant_TrailingDonchian(ExitVariant):
    """
    SL inicial = 1.5×ATR.  Sin TP fijo.
    Trailing basado en el canal Donchian: el SL se desplaza al mínimo de las
    últimas PERIOD velas (BUY) o al máximo (SELL), calculado en cada barra.
    Solo avanza en dirección favorable — nunca retrocede.

    El canal Donchian es más adaptativo que un múltiplo fijo de ATR:
    en mercados con tendencia fuerte y bajo rango el SL queda más ajustado,
    mientras que en volatilidad alta da más espacio al trade.
    """
    name  = "trailing_donchian"
    label = "Trailing Donchian (10 velas)"

    ATR_INIT_MULT = 1.5   # SL inicial
    PERIOD        = 10    # velas para el canal Donchian

    def compute_levels(self, entry, direction, atr, df_window):
        sl_dist = atr * self.ATR_INIT_MULT
        sl = entry - sl_dist if direction == "BUY" else entry + sl_dist
        return sl, None

    def simulate_exit(self, entry, sl, tp, direction, df_full, start_index, atr_at_entry):
        ps = self.pip_size
        current_sl = sl

        for i in range(start_index + 1, min(start_index + self.max_forward, len(df_full))):
            high  = float(df_full.iloc[i]["high"])
            low   = float(df_full.iloc[i]["low"])

            # Calcular nivel Donchian sobre las PERIOD velas anteriores a i
            lookback_start = max(0, i - self.PERIOD)
            if direction == "BUY":
                # SL = mínimo del canal de las últimas PERIOD velas (low)
                donchian_sl = float(df_full["low"].iloc[lookback_start:i].min())
                if donchian_sl > current_sl:          # solo sube
                    current_sl = donchian_sl
                if low <= current_sl:
                    raw = (current_sl - entry) / ps
                    mae, mfe = _calc_mae_mfe(direction, entry, df_full, start_index, i, ps)
                    return ExitResult(
                        "WIN" if current_sl > entry else "LOSS",
                        current_sl, i, _net_pips(raw), mae, mfe,
                    )
            else:  # SELL
                # SL = máximo del canal de las últimas PERIOD velas (high)
                donchian_sl = float(df_full["high"].iloc[lookback_start:i].max())
                if donchian_sl < current_sl:          # solo baja
                    current_sl = donchian_sl
                if high >= current_sl:
                    raw = (entry - current_sl) / ps
                    mae, mfe = _calc_mae_mfe(direction, entry, df_full, start_index, i, ps)
                    return ExitResult(
                        "WIN" if current_sl < entry else "LOSS",
                        current_sl, i, _net_pips(raw), mae, mfe,
                    )

        return ExitResult("PENDING", None, None, 0.0, 0.0, 0.0)


# ══════════════════════════════════════════════════════════════════════════════
# VARIANTE 12: Time Exit — cierre automático tras N velas
# ══════════════════════════════════════════════════════════════════════════════

class Variant_TimeExit(ExitVariant):
    """
    SL inicial = 1.5×ATR.  Sin TP fijo.
    Cierra automáticamente la posición al precio de cierre de la vela
    número MAX_BARS después de la entrada, independientemente del resultado.

    Si el SL es tocado antes de que expire el tiempo, el SL tiene prioridad.

    Útil para investigar si la estrategia captura su edge en las primeras
    horas y las salidas largas dañan los resultados.
    MAX_BARS = 48 ≈ 2 días H1.  Configurable como atributo de clase.
    """
    name  = "time_exit"
    label = "Time Exit (48 velas H1)"

    ATR_INIT_MULT = 1.5
    MAX_BARS      = 48    # número de velas antes del cierre forzado

    def compute_levels(self, entry, direction, atr, df_window):
        sl_dist = atr * self.ATR_INIT_MULT
        sl = entry - sl_dist if direction == "BUY" else entry + sl_dist
        return sl, None

    def simulate_exit(self, entry, sl, tp, direction, df_full, start_index, atr_at_entry):
        ps = self.pip_size
        current_sl = sl
        end_index  = min(start_index + self.MAX_BARS + 1, len(df_full))

        for bars_held, i in enumerate(range(start_index + 1, end_index), start=1):
            high  = float(df_full.iloc[i]["high"])
            low   = float(df_full.iloc[i]["low"])
            close = float(df_full.iloc[i]["close"])

            # Comprobar SL (tiene prioridad sobre el cierre temporal)
            if direction == "BUY":
                if low <= current_sl:
                    raw = (current_sl - entry) / ps
                    mae, mfe = _calc_mae_mfe(direction, entry, df_full, start_index, i, ps)
                    return ExitResult(
                        "WIN" if current_sl > entry else "LOSS",
                        current_sl, i, _net_pips(raw), mae, mfe,
                    )
            else:
                if high >= current_sl:
                    raw = (entry - current_sl) / ps
                    mae, mfe = _calc_mae_mfe(direction, entry, df_full, start_index, i, ps)
                    return ExitResult(
                        "WIN" if current_sl < entry else "LOSS",
                        current_sl, i, _net_pips(raw), mae, mfe,
                    )

            # Cierre temporal al llegar al límite de velas
            if bars_held >= self.MAX_BARS:
                if direction == "BUY":
                    raw = (close - entry) / ps
                else:
                    raw = (entry - close) / ps
                result = "WIN" if raw >= 0 else "LOSS"
                mae, mfe = _calc_mae_mfe(direction, entry, df_full, start_index, i, ps)
                return ExitResult(result, close, i, _net_pips(raw), mae, mfe)

        # Si se agotó max_forward sin cerrar (no debería ocurrir con MAX_BARS ≤ max_forward)
        return ExitResult("PENDING", None, None, 0.0, 0.0, 0.0)


# ══════════════════════════════════════════════════════════════════════════════
# REGISTRO DE VARIANTES
# ══════════════════════════════════════════════════════════════════════════════

ALL_VARIANTS: list[ExitVariant] = [
    Variant_RR2(),
    Variant_RR25(),
    Variant_RR3(),
    Variant_RR35(),
    Variant_RR4(),
    Variant_TrailingATR(),
    Variant_TrailingEMA(),
    Variant_DynamicATR(),
    Variant_BreakEven(),
    Variant_PartialClose(),
    Variant_TrailingDonchian(),
    Variant_TimeExit(),
]

VARIANT_BY_NAME: dict[str, ExitVariant] = {v.name: v for v in ALL_VARIANTS}
