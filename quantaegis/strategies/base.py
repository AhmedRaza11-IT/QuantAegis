from abc import ABC, abstractmethod
import pandas as pd
from quantaegis.core.events import OHLCVBar, SignalEvent
from typing import Optional

class BaseStrategy(ABC):
    name: str
    
    @abstractmethod
    def on_bar(self, bar: OHLCVBar, htf_data: pd.DataFrame, ltf_data: pd.DataFrame) -> Optional[SignalEvent]:
        """Process a new bar. HTF = higher timeframe df, LTF = lower timeframe df. Return SignalEvent or None."""
        ...
    
    @abstractmethod
    def reset(self) -> None:
        """Reset internal state."""
        ...
