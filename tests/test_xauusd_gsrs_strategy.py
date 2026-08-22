"""
Tests para GSRS (Gold Session Reversal Strategy)
=================================================
Verifica el correcto funcionamiento de:
1. Algoritmo de detección de giros/pivotes (detect_swings).
2. Detección de Type 3 Shift (alcista y bajista).
3. Transiciones de estado de GSRSStrategy.
4. Adaptador XAUUSDGSRSStrategy e integración con la infraestructura del laboratorio.
"""

from datetime import datetime, time, timezone, timedelta
import pytest
import pandas as pd
import numpy as np

from strategies.experimental.gold_newstrat import (
    GSRSConfig,
    GSRSState,
    GSRSStrategy,
    XAUUSDGSRSStrategy,
    Candle,
    SwingPoint,
    TradeSetup,
)
from strategies.experimental.gold_newstrat.gsrs_strategy import (
    detect_swings,
    check_type3_shift,
    pullback_entry_level,
    compute_stop_loss,
    compute_take_profit,
)
from strategies import STRATEGY_REGISTRY
from core.exit_research.strategy_adapter import adapter_for_symbol, StrategyAdapter


def test_detect_swings_fractal():
    cfg = GSRSConfig(swing_fractal_strength=2)
    # Crear secuencia con un máximo en la vela 2 y un mínimo en la vela 5
    # indices: 0, 1, 2 (High 100), 3, 4, 5 (Low 50), 6, 7
    base_time = datetime(2026, 1, 1, 0, 0, tzinfo=timezone.utc)
    prices = [
        (10, 5),   # 0
        (12, 6),   # 1
        (20, 8),   # 2 - Swing High (20)
        (15, 7),   # 3
        (11, 6),   # 4
        (14, 2),   # 5 - Swing Low (2)
        (15, 8),   # 6
        (16, 9),   # 7
    ]
    candles = [
        Candle(time=base_time + timedelta(minutes=i), open=p[0], high=p[0], low=p[1], close=p[0])
        for i, p in enumerate(prices)
    ]

    swings = detect_swings(candles, cfg)
    assert len(swings) == 2
    assert swings[0].kind == "high"
    assert swings[0].price == 20.0
    assert swings[0].index == 2

    assert swings[1].kind == "low"
    assert swings[1].price == 2.0
    assert swings[1].index == 5


def test_check_type3_shift_bearish():
    # Sequence: L1 -> H1 -> L2 (HL) -> H2 (HH) -> L3 (< L1)
    base_time = datetime(2026, 1, 1, 0, 0, tzinfo=timezone.utc)
    swings = [
        SwingPoint(index=1, time=base_time, price=100.0, kind="low"),
        SwingPoint(index=2, time=base_time, price=120.0, kind="high"),
        SwingPoint(index=3, time=base_time, price=105.0, kind="low"),   # HL > L1
        SwingPoint(index=4, time=base_time, price=130.0, kind="high"),  # HH > H1 (External High)
        SwingPoint(index=5, time=base_time, price=95.0, kind="low"),    # L3 < L1 (Break)
    ]

    setup = check_type3_shift(swings)
    assert setup is not None
    assert setup.direction == "short"
    assert setup.external_level == 130.0
    assert setup.break_high == 130.0
    assert setup.break_low == 95.0


def test_check_type3_shift_bullish():
    # Sequence: H1 -> L1 -> H2 (LH) -> L2 (LL) -> H3 (> H1)
    base_time = datetime(2026, 1, 1, 0, 0, tzinfo=timezone.utc)
    swings = [
        SwingPoint(index=1, time=base_time, price=200.0, kind="high"),
        SwingPoint(index=2, time=base_time, price=180.0, kind="low"),
        SwingPoint(index=3, time=base_time, price=195.0, kind="high"),  # LH < H1
        SwingPoint(index=4, time=base_time, price=170.0, kind="low"),   # LL < L1 (External Low)
        SwingPoint(index=5, time=base_time, price=210.0, kind="high"),  # H3 > H1 (Break)
    ]

    setup = check_type3_shift(swings)
    assert setup is not None
    assert setup.direction == "long"
    assert setup.external_level == 170.0
    assert setup.break_high == 210.0
    assert setup.break_low == 170.0


def test_sl_tp_and_pullback_calculations():
    cfg = GSRSConfig(
        pullback_fraction=0.5,
        sl_buffer_fraction_of_break=0.10,
        tp_overextension_fraction=0.5
    )
    setup = TradeSetup(
        direction="short",
        external_level=130.0,
        break_high=130.0,
        break_low=90.0,
    )

    entry = pullback_entry_level(setup, cfg)
    assert entry == 110.0  # midpoint of 90 and 130

    sl = compute_stop_loss(setup, cfg)
    # break_range = 40, buffer = 4.0, short SL = 130 + 4 = 134
    assert sl == 134.0

    # Overextension = |140 - 100| = 40, 50% TP distance = 20
    tp = compute_take_profit(setup, h1_open=100.0, h1_extreme=140.0, config=cfg)
    assert tp == 80.0  # 100 - 20


def test_gsrs_strategy_state_transitions():
    cfg = GSRSConfig(
        session_windows_utc={"test_window": (time(0, 0), time(1, 0))},
        expansion_min_atr_multiple=1.0,
        expansion_lookback_minutes=2,
        swing_fractal_strength=1,
    )
    strat = GSRSStrategy(cfg)

    # 1. Outside window -> WAIT_SESSION
    c0 = Candle(time=datetime(2026, 1, 1, 2, 0, tzinfo=timezone.utc), open=2000, high=2001, low=1999, close=2000)
    strat.on_new_candle(c0)
    assert strat.state == GSRSState.WAIT_SESSION

    # 2. Inside window -> WAIT_EXPANSION
    c1 = Candle(time=datetime(2026, 1, 1, 0, 1, tzinfo=timezone.utc), open=2000, high=2002, low=1998, close=2000)
    strat.on_new_candle(c1)
    assert strat.state == GSRSState.WAIT_EXPANSION

    # 3. Large move -> WAIT_SHIFT
    c2 = Candle(time=datetime(2026, 1, 1, 0, 2, tzinfo=timezone.utc), open=2000, high=2050, low=1998, close=2045)
    strat.on_new_candle(c2)
    assert strat.state == GSRSState.WAIT_SHIFT


def test_xauusd_gsrs_basestrategy_integration():
    strategy = XAUUSDGSRSStrategy()
    assert strategy.name == "xauusd_gsrs"
    assert strategy.metadata.symbol == "XAUUSD"
    assert strategy.metadata.timeframe == "M1"
    assert strategy.metadata.required_history == 120

    # Config default dict
    cfg = strategy._get_default_config()
    assert cfg['symbol'] == "XAUUSD"
    assert 'expansion_min_atr_multiple' in cfg

    # Test detect_setup on dummy df
    dates = pd.date_range("2026-01-01 00:00:00", periods=20, freq="1min", tz="UTC")
    df = pd.DataFrame({
        'time': dates,
        'open': np.linspace(2000, 2010, 20),
        'high': np.linspace(2002, 2012, 20),
        'low': np.linspace(1998, 2008, 20),
        'close': np.linspace(2001, 2011, 20),
    })

    # Should run without error
    signal = strategy.detect_setup(df)
    assert signal is None or isinstance(signal, dict)


def test_registry_and_adapter_discovery():
    # 1. Registry in strategies
    assert 'XAUUSD_GSRS' in STRATEGY_REGISTRY
    instance = STRATEGY_REGISTRY['XAUUSD_GSRS']()
    assert isinstance(instance, XAUUSDGSRSStrategy)

    # 2. StrategyAdapter in core/exit_research/strategy_adapter.py
    adapter = adapter_for_symbol("XAUUSD_GSRS")
    assert isinstance(adapter, StrategyAdapter)
    assert adapter.name == "xauusd_gsrs"
