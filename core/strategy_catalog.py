"""
Strategy Catalog & Metadata Registry

Centralized source of truth for supported symbols, strategies, and timeframes.
Allows dynamic expansion without hardcoding in frontend applications.
Automatically scans strategies/, strategies/vault/, strategies/private/ and
manifests to discover new strategies dynamically on the fly.
"""

from __future__ import annotations

import os
import json
import logging
import importlib.util
from pathlib import Path
from typing import Dict, List, Any, Optional

logger = logging.getLogger(__name__)

# Baseline static registry ensuring immediate zero-latency startup
BASE_STRATEGY_CATALOG: Dict[str, Dict[str, Any]] = {
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
            },
            {
                "id": "eurusd_simple",
                "name": "EURUSD Simple Baseline",
                "description": "Baseline trend following with EMA20/50 and ATR trailing stop",
                "allowed_timeframes": ["H1"],
                "default_timeframe": "H1",
                "lookback_min": 200,
            },
            {
                "id": "eurusd_flow",
                "name": "EURUSD Flow Strategy (v1.0)",
                "description": "Institutional flow, liquidity sweeps and EMA pullback rejection",
                "allowed_timeframes": ["H1"],
                "default_timeframe": "H1",
                "lookback_min": 200,
            }
        ]
    },

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
            },
            {
                "id": "xauusd_surge",
                "name": "XAUUSD Surge Strategy (v1.0)",
                "description": "Volatility squeeze breakout & Donchian trend expansion",
                "allowed_timeframes": ["H1"],
                "default_timeframe": "H1",
                "lookback_min": 200,
            },
            {
                "id": "xauusd_asian_london",
                "name": "XAUUSD Asian-London Strategy (v1.0)",
                "description": "Asian range liquidity sweep & London opening volatility expansion",
                "allowed_timeframes": ["H1"],
                "default_timeframe": "H1",
                "lookback_min": 200,
            }
        ]
    },

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
            },
            {
                "id": "btceur_trend_surge",
                "name": "BTCEUR Trend Surge (v1.0)",
                "description": "H4 macro regime filter with H1 EMA20 touch & ATR expansion",
                "allowed_timeframes": ["H1"],
                "default_timeframe": "H1",
                "lookback_min": 850,
            }
        ]
    }
}

# In-memory working copy
STRATEGY_CATALOG: Dict[str, Dict[str, Any]] = json.loads(json.dumps(BASE_STRATEGY_CATALOG))


def _clean_display_name(identifier: str) -> str:
    """Converts a snake_case strategy id into a clean title."""
    parts = identifier.replace("-", "_").split("_")
    cleaned = []
    for p in parts:
        if p.upper() in ("BTC", "EUR", "USD", "XAU", "ATR", "RSI", "EMA", "SMA", "GSRS", "WFA"):
            cleaned.append(p.upper())
        elif p.lower() in ("v1", "v2", "v3"):
            cleaned.append(f"({p})")
        else:
            cleaned.append(p.capitalize())
    return " ".join(cleaned)


def discover_dynamic_strategies() -> None:
    """
    Scans the strategies directories (root, vault, private, experimental)
    and dynamically registers any new BaseStrategy implementations or packages.
    """
    try:
        from strategies.base import BaseStrategy
        import strategies as strat_pkg
    except Exception as e:
        logger.debug("[StrategyCatalog] BaseStrategy import deferred: %s", e)
        return

    # Base search directories
    pkg_dir = Path(__file__).resolve().parent.parent / "strategies"
    search_dirs = [
        pkg_dir,
        pkg_dir / "public",
        pkg_dir / "vault",
        pkg_dir / "private",
        pkg_dir / "experimental",
    ]

    for sdir in search_dirs:
        if not sdir.exists() or not sdir.is_dir():
            continue

        # 1. Discover standalone Python strategy files
        for py_path in sdir.glob("*.py"):
            if py_path.name.startswith(("_", ".")) or py_path.name in ("base.py", "setup.py", "conftest.py"):
                continue

            strat_id = py_path.stem.lower()

            try:
                mod_name = f"dyn_cat_{py_path.stem}"
                spec = importlib.util.spec_from_file_location(mod_name, py_path)
                if not spec or not spec.loader:
                    continue
                mod = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(mod)

                for attr in dir(mod):
                    cls = getattr(mod, attr)
                    if isinstance(cls, type) and issubclass(cls, BaseStrategy) and cls is not BaseStrategy:
                        # Determine Symbol
                        sym = "EURUSD"
                        if "xau" in strat_id or "gold" in strat_id:
                            sym = "XAUUSD"
                        elif "btc" in strat_id:
                            sym = "BTCEUR"

                        tfs = ["H1"]
                        lookback = 200
                        desc = (cls.__doc__ or f"Estrategia cuantitativa dinámica {strat_id}").strip().split("\n")[0]
                        friendly_name = _clean_display_name(strat_id)

                        try:
                            inst = cls()
                            if hasattr(inst, "strategy_name") and inst.strategy_name:
                                strat_id = str(inst.strategy_name).lower()
                            if hasattr(inst, "metadata") and inst.metadata:
                                meta = inst.metadata
                                if hasattr(meta, "symbol") and meta.symbol:
                                    sym = str(meta.symbol).upper()
                                if hasattr(meta, "timeframe") and meta.timeframe:
                                    tfs = [str(meta.timeframe).upper()]
                                if hasattr(meta, "required_history") and meta.required_history:
                                    lookback = int(meta.required_history)
                        except Exception:
                            pass

                        # Register dynamically in STRATEGY_REGISTRY
                        if hasattr(strat_pkg, "STRATEGY_REGISTRY"):
                            strat_pkg.STRATEGY_REGISTRY[strat_id] = cls
                            strat_pkg.STRATEGY_REGISTRY[strat_id.upper()] = cls

                        # Add to STRATEGY_CATALOG if not already present
                        if sym not in STRATEGY_CATALOG:
                            STRATEGY_CATALOG[sym] = {
                                "symbol": sym,
                                "name": sym,
                                "asset_class": "Crypto" if "BTC" in sym or "ETH" in sym else "Commodities" if "XAU" in sym else "Forex",
                                "strategies": []
                            }

                        existing_ids = [s["id"].lower() for s in STRATEGY_CATALOG[sym]["strategies"]]
                        if strat_id not in existing_ids:
                            STRATEGY_CATALOG[sym]["strategies"].append({
                                "id": strat_id,
                                "name": friendly_name,
                                "description": desc,
                                "allowed_timeframes": tfs,
                                "default_timeframe": tfs[0],
                                "lookback_min": lookback,
                            })
                            logger.info("[StrategyCatalog] Dynamically registered strategy '%s' under symbol '%s'", strat_id, sym)
            except Exception as e:
                logger.debug("[StrategyCatalog] Could not inspect file %s: %s", py_path.name, e)

        # 2. Discover JSON manifests (promoted packages)
        for json_path in sdir.glob("*.json"):
            if json_path.name.startswith(("_", ".")):
                continue
            try:
                with open(json_path, "r", encoding="utf-8") as f:
                    manifest = json.load(f)
                if not isinstance(manifest, dict) or "strategy_name" not in manifest or "symbol" not in manifest:
                    continue

                sym = manifest["symbol"].upper()
                s_id = manifest.get("strategy_id", json_path.stem).lower()
                s_name = manifest.get("strategy_name", _clean_display_name(s_id))
                s_tfs = manifest.get("allowed_timeframes", ["H1"])
                s_def_tf = manifest.get("default_timeframe", s_tfs[0] if s_tfs else "H1")
                s_lookback = manifest.get("lookback_min", 200)
                s_desc = manifest.get("description", "Estrategia promovida y validada científicamente")

                if sym not in STRATEGY_CATALOG:
                    STRATEGY_CATALOG[sym] = {
                        "symbol": sym,
                        "name": sym,
                        "asset_class": "Crypto" if "BTC" in sym else "Forex",
                        "strategies": []
                    }

                existing_ids = [s["id"].lower() for s in STRATEGY_CATALOG[sym]["strategies"]]
                if s_id not in existing_ids:
                    STRATEGY_CATALOG[sym]["strategies"].append({
                        "id": s_id,
                        "name": s_name,
                        "description": s_desc,
                        "allowed_timeframes": s_tfs,
                        "default_timeframe": s_def_tf,
                        "lookback_min": s_lookback,
                    })
            except Exception:
                pass


def get_strategy_catalog() -> Dict[str, Any]:
    """
    Returns the full strategy catalog payload for API consumers.
    Triggers dynamic discovery so newly added strategy files are returned instantly.
    """
    discover_dynamic_strategies()

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
    discover_dynamic_strategies()
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
