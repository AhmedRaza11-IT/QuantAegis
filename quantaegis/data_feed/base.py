from abc import ABC, abstractmethod
from typing import AsyncIterator
import pandas as pd
from quantaegis.core.events import OHLCVBar

class BaseDataFeed(ABC):
    """Abstract interface for all data feed connectors."""
    
    @abstractmethod
    async def connect(self) -> None: ...
    
    @abstractmethod
    async def disconnect(self) -> None: ...
    
    @abstractmethod
    async def stream(self) -> AsyncIterator[OHLCVBar]: ...
    
    @abstractmethod
    async def get_historical_ohlcv(
        self, symbol: str, timeframe: str, count: int
    ) -> pd.DataFrame: ...
    
    @property
    @abstractmethod
    def is_connected(self) -> bool: ...
