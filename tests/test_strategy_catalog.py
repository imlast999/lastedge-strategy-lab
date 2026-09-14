"""
Tests for Strategy Catalog and dynamic strategy/timeframe validation.
"""

import pytest
from core.strategy_catalog import (
    get_strategy_catalog,
    get_strategies_for_symbol,
    get_strategy_metadata,
    get_allowed_timeframes,
)
from services.backtest_service import BacktestService


def test_strategy_catalog_structure():
    catalog = get_strategy_catalog()
    assert catalog["ok"] is True
    assert "EURUSD" in catalog["symbols"]
    assert "XAUUSD" in catalog["symbols"]
    assert "BTCEUR" in catalog["symbols"]

    # EURUSD has 1 strategy
    eur_strats = catalog["strategies"]["EURUSD"]
    assert len(eur_strats) == 1
    assert eur_strats[0]["id"] == "eurusd_partial"
    assert eur_strats[0]["allowed_timeframes"] == ["H1"]

    # XAUUSD has 2 strategies
    xau_strats = catalog["strategies"]["XAUUSD"]
    assert len(xau_strats) == 2
    xau_ids = [s["id"] for s in xau_strats]
    assert "xauusd_partial" in xau_ids
    assert "xauusd_simple" in xau_ids

    # BTCEUR has 5 strategies
    btc_strats = catalog["strategies"]["BTCEUR"]
    assert len(btc_strats) == 5
    btc_ids = [s["id"] for s in btc_strats]
    assert "btceur_partial" in btc_ids
    assert "btceur_simple" in btc_ids
    assert "btc_trend_pullback_v1" in btc_ids
    assert "btceur_regime_momentum" in btc_ids
    assert "btceur_weekly_breakout" in btc_ids

    # Regime momentum requires H4
    regime_meta = get_strategy_metadata("BTCEUR", "btceur_regime_momentum")
    assert regime_meta is not None
    assert regime_meta["allowed_timeframes"] == ["H4"]
    assert regime_meta["default_timeframe"] == "H4"


def test_backtest_rejects_cross_pair_strategy():
    service = BacktestService()
    # Try running a BTCEUR strategy on EURUSD
    res = service.run_backtest(symbol="EURUSD", strategy_name="btc_trend_pullback_v1", bars=300)
    assert res["ok"] is False
    assert "no es válida para el par EURUSD" in res["error"]


def test_backtest_auto_adjusts_restricted_timeframe():
    service = BacktestService()
    # btceur_regime_momentum requires H4. If passed M15, it adjusts to H4
    res = service.run_backtest(
        symbol="BTCEUR",
        strategy_name="btceur_regime_momentum",
        timeframe="M15",
        bars=1100,
    )
    assert res["ok"] is True
    assert res["timeframe"] == "H4"
