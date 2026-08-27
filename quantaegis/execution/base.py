from abc import ABC, abstractmethod
from typing import Dict, Any, List

from quantaegis.core.events import SignalEvent, OrderEvent

class BaseExecutor(ABC):
    @abstractmethod
    async def place_order(self, signal: SignalEvent, lots: float) -> OrderEvent:
        pass
    
    @abstractmethod
    async def close_order(self, order_id: str, symbol: str) -> OrderEvent:
        pass
    
    @abstractmethod
    async def get_account_info(self) -> Dict[str, Any]:
        pass
    
    @abstractmethod
    async def get_open_positions(self) -> List[Dict[str, Any]]:
        pass
    
    @abstractmethod
    async def get_current_spread(self, symbol: str) -> float:
        pass
