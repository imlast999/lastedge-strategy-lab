"""
Strategy Catalog & Metadata Registry

Centralized source of truth for supported symbols, strategies, and timeframes.
Allows dynamic expansion without hardcoding in frontend applications.
"""

import logging
from typing import Dict, List, Any, Optional

logger = logging.getLogger(__name__)

STRATEGY_CATALOG: Dict[str, Dict[str, Any]] = {
    # ── EURUSD (1 Strategy) ────────────────────────────────────────────────
    "EURUSD": {
        "symbol": "EURUSD",
        "name": "Euro / US Dollar",
        "asset_class": "Forex",
        "strategies": [
            {
                "id": "eurusd_partial",
                "name": "EURUSD Partial Close (v1.1)",
                "description": "Trend momentum with EMA20/50/200, RSI and dynamic ATR partial closes",
                "allowed_timeframes": ["H1"],
                "default_timeframe": "H1",
                "lookback_min": 200,
            }
        ]
    },

    # ── XAUUSD (2 Strategies) ──────────────────────────────────────────────
    "XAUUSD": {
        "symbol": "XAUUSD",
        "name": "Gold / US Dollar",
        "asset_class": "Commodities",
        "strategies": [
            {
                "id": "xauusd_partial",
                "name": "XAUUSD Partial Close (v1.1)",
                "description": "Selective Gold momentum reversal with multi-stage partial TP",
                "allowed_timeframes": ["H1"],
                "default_timeframe": "H1",
                "lookback_min": 200,
            },
            {
                "id": "xauusd_simple",
                "name": "XAUUSD Simple Baseline",
                "description": "Gold trend baseline with EMA200 trend filter and RSI momentum",
                "allowed_timeframes": ["H1"],
                "default_timeframe": "H1",
                "lookback_min": 200,
            }
        ]
    },

    # ── BTCEUR (5 Strategies) ──────────────────────────────────────────────
    "BTCEUR": {
        "symbol": "BTCEUR",
        "name": "Bitcoin / Euro",
        "asset_class": "Crypto",
        "strategies": [
            {
                "id": "btceur_partial",
                "name": "BTCEUR Partial Close (v1.1)",
                "description": "Simplified Bitcoin trend & volatility with partial take profit",
                "allowed_timeframes": ["H1"],
                "default_timeframe": "H1",
                "lookback_min": 300,
            },
            {
                "id": "btceur_simple",
                "name": "BTCEUR Simple Baseline",
                "description": "Baseline trend & volatility breakout for Bitcoin EUR",
                "allowed_timeframes": ["H1"],
                "default_timeframe": "H1",
                "lookback_min": 300,
            },
            {
                "id": "btc_trend_pullback_v1",
                "name": "BTC Trend Pullback v1",
                "description": "Swing trading combining H4 macro trend filter with H1 EMA20 pullbacks",
                "allowed_timeframes": ["H1"],
                "default_timeframe": "H1",
                "lookback_min": 850,
            },
            {
                "id": "btceur_regime_momentum",
                "name": "BTCEUR Regime Momentum",
                "description": "Daily regime filter (EMA50>200, ADX>20) + H4 Donchian breakout (Long only)",
                "allowed_timeframes": ["H4"],
                "default_timeframe": "H4",
                "lookback_min": 900,
            },
            {
                "id": "btceur_weekly_breakout",
                "name": "BTCEUR Weekly Breakout",
                "description": "Weekly range breakout capturing institutional weekly expansion waves",
                "allowed_timeframes": ["H1"],
                "default_timeframe": "H1",
                "lookback_min": 900,
            }
        ]
    }
}


def get_strategy_catalog() -> Dict[str, Any]:
    """Returns the full strategy catalog payload for API consumers."""
    symbols = list(STRATEGY_CATALOG.keys())
    strategies_by_symbol: Dict[str, List[Dict[str, Any]]] = {}
    for sym, data in STRATEGY_CATALOG.items():
        strategies_by_symbol[sym] = data["strategies"]

    return {
        "ok": True,
        "symbols": symbols,
        "strategies": strategies_by_symbol,
        "catalog": STRATEGY_CATALOG,
    }


def get_strategies_for_symbol(symbol: str) -> List[Dict[str, Any]]:
    """Returns the list of valid strategies for a specific symbol."""
    sym_upper = symbol.upper()
    data = STRATEGY_CATALOG.get(sym_upper)
    if not data:
        return []
    return data.get("strategies", [])


def get_strategy_metadata(symbol: str, strategy_id: str) -> Optional[Dict[str, Any]]:
    """Finds metadata for a specific symbol and strategy ID."""
    strategies = get_strategies_for_symbol(symbol)
    strat_lower = strategy_id.lower().strip()
    for s in strategies:
        if s["id"].lower() == strat_lower:
            return s
    return None


def get_allowed_timeframes(symbol: str, strategy_id: str) -> List[str]:
    """Returns allowed timeframes for a given symbol and strategy."""
    meta = get_strategy_metadata(symbol, strategy_id)
    if meta and "allowed_timeframes" in meta:
        return meta["allowed_timeframes"]
    return ["H1"]
