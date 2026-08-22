# LastEdge Strategy Lab — Unified Strategy Contract

> **Module:** `LastEdge Strategy Lab`  
> **Source File:** `strategies/base.py`  

---

## 1. Unified Contract Definition

Strategy Lab uses the identical abstract contract `BaseStrategy` and `StrategyMetadata` as Trading Engine.

```python
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Dict, Any, Optional
import pandas as pd

@dataclass
class StrategyMetadata:
    required_history: int       # Minimum warmup bars
    symbol: str                 # Trading symbol
    timeframe: str              # Timeframe string
    strategy_name: str          # Canonical strategy identifier
    version: str                # Semantic version (vX.Y.Z)

class BaseStrategy(ABC):
    @property
    @abstractmethod
    def metadata(self) -> StrategyMetadata: pass

    @abstractmethod
    def _get_default_config(self) -> Dict[str, Any]: pass

    @abstractmethod
    def _add_specific_indicators(self, df: pd.DataFrame, config: Dict[str, Any]) -> pd.DataFrame: pass

    @abstractmethod
    def detect_setup(self, df: pd.DataFrame, config: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]: pass
```
