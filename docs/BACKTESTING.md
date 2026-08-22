# LastEdge Strategy Lab — Backtesting & Realistic Cost Modeling

> **Module:** `LastEdge Strategy Lab`  
> **Source Files:** `core/replay_engine.py`, `core/trade_costs.py`  

---

## 1. Backtesting Philosophy

Backtesting without transaction costs produces deceptive results. LastEdge incorporates realistic market frictions on every simulated trade:

$$\text{Net PnL} = \text{Gross PnL} - \text{Spread Cost} - \text{Commission} - \text{Slippage}$$

---

## 2. Trade Cost Modeling (`core/trade_costs.py`)

- **Spread Cost**: Deducts entry and exit half-spreads based on instrument historical spread distributions.
- **Broker Commission**: Computes round-turn commission per standard lot (e.g. $6.00 / lot on ECN/Raw accounts).
- **Slippage Model**: Uses stochastic or volatility-adjusted slippage penalties to simulate volatile market fills.

---

## 3. Bar-by-Bar Replay Engine (`core/replay_engine.py`)

The replay engine processes OHLCV and tick bars sequentially:
1. Warmup period: Feeds `required_history` bars to initialize indicators.
2. Signal trigger: Evaluates `detect_setup(df_window)` on bar close.
3. Intrabar execution: Simulates fill prices using next bar Open/High/Low to verify exact Stop Loss or Take Profit execution.
