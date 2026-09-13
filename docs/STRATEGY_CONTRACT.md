# LastEdge — Canonical Strategy Contract & Authoring Guide

> **Master Specification:** `LastEdge Strategy Lab` (Canonical Authoring Authority)  
> **Target Package:** `strategies/base.py`  
> **Status:** Production Standard  

---

## 1. Unified Strategy Contract Definition

Every trading strategy in the LastEdge platform is an immutable, object-oriented model inheriting from `BaseStrategy`. Research prototypes and Production execution models share the exact same interface:

```python
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Dict, Any, Optional
import pandas as pd


@dataclass
class StrategyMetadata:
    required_history: int       # Number of warmup bars required (invariable: minimum 50 bars)
    symbol: str                 # Trading symbol (e.g. 'EURUSD', 'XAUUSD', 'BTCEUR')
    timeframe: str              # Timeframe string (e.g. 'H1', 'M15')
    strategy_name: str          # Canonical strategy identifier
    version: str                # Semantic version (e.g. '1.0.0')

    def __post_init__(self):
        if self.required_history < 50:
            raise ValueError("required_history must be >= 50 for indicator stability.")


class BaseStrategy(ABC):
    def __init__(self, name: str):
        self.name = name
        self.default_config = self._get_default_config()

    @property
    @abstractmethod
    def metadata(self) -> StrategyMetadata:
        """Returns the immutable metadata specification of the strategy."""
        pass

    @abstractmethod
    def _get_default_config(self) -> Dict[str, Any]:
        """Returns baseline hyperparameters dictionary."""
        pass

    @abstractmethod
    def _add_specific_indicators(self, df: pd.DataFrame, config: Dict[str, Any]) -> pd.DataFrame:
        """Calculates indicators and appends columns to the DataFrame."""
        pass

    @abstractmethod
    def detect_setup(self, df: pd.DataFrame, config: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
        """
        Scans the current bar for entry setups.
        Returns:
            Dict: {'type': 'BUY'|'SELL', 'entry': float, 'sl': float, 'tp': float, 'context': dict}
            None: if no trade setup is detected.
        """
        pass
```

---

## 2. Standard Signal Return Dictionary

When `detect_setup(df)` detects an entry setup, it must return:

```json
{
  "type": "BUY",
  "entry": 1.08500,
  "sl": 1.08100,
  "tp": 1.09300,
  "timeframe": "H1",
  "context": {
    "atr": 0.00267,
    "ema_fast": 1.08450,
    "ema_slow": 1.08200
  }
}
```

---

## 3. Creating a New Strategy Prototype (`strategies/experimental/`)

To develop a new candidate model in Strategy Lab:
1. Create `strategies/experimental/my_strategy.py`.
2. Inherit from `BaseStrategy`.
3. Provide `StrategyMetadata` with `required_history >= 50`.
4. Implement vector indicators and signal logic.

```python
from strategies.base import BaseStrategy, StrategyMetadata
import pandas as pd

class CustomAsianBreakout(BaseStrategy):
    def __init__(self):
        super().__init__(name="eurusd_asian_breakout")

    @property
    def metadata(self) -> StrategyMetadata:
        return StrategyMetadata(
            required_history=100,
            symbol="EURUSD",
            timeframe="H1",
            strategy_name="eurusd_asian_breakout",
            version="1.0.0"
        )

    def _get_default_config(self):
        return {"asian_start": "00:00", "asian_end": "07:00", "sl_pips": 15.0}

    def _add_specific_indicators(self, df: pd.DataFrame, config):
        # Add session ranges
        return df

    def detect_setup(self, df: pd.DataFrame, config=None):
        if len(df) < self.metadata.required_history:
            return None
        # Evaluate setup...
        return None
```
