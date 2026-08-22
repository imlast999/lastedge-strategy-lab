# LastEdge Strategy Lab — Strategy Generation & Creation Guide

> **Module:** `LastEdge Strategy Lab`  
> **Source Directory:** `strategies/experimental/`  

---

## 1. Creating a New Candidate Strategy

To develop a new strategy in Strategy Lab:

1. Create a new file in `strategies/experimental/my_strategy.py`.
2. Inherit from `BaseStrategy` defined in `strategies/base.py`.
3. Define `StrategyMetadata` with unique name, version, and warmup history.
4. Implement `_get_default_config()`, `_add_specific_indicators()`, and `detect_setup()`.

---

## 2. Code Example Template

```python
from typing import Dict, Any, Optional
import pandas as pd
from strategies.base import BaseStrategy, StrategyMetadata

class MyCustomStrategy(BaseStrategy):
    @property
    def metadata(self) -> StrategyMetadata:
        return StrategyMetadata(
            required_history=100,
            symbol="EURUSD",
            timeframe="H1",
            strategy_name="eurusd_my_custom",
            version="1.0.0"
        )

    def _get_default_config(self) -> Dict[str, Any]:
        return {"ema_period": 20, "atr_multiplier": 1.5}

    def _add_specific_indicators(self, df: pd.DataFrame, config: Dict[str, Any]) -> pd.DataFrame:
        df["ema"] = df["close"].ewm(span=config["ema_period"]).mean()
        return df

    def detect_setup(self, df: pd.DataFrame, config: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
        # Evaluation logic...
        return None
```
