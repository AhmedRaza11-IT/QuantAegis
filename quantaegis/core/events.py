import asyncio
from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal, Optional, Callable, Awaitable, Dict, List, Type
from collections import defaultdict
import structlog

logger = structlog.get_logger(__name__)

@dataclass
class OHLCVBar:
    symbol: str
    timeframe: str
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float
    source: str  # 'mt5' or 'ccxt'

@dataclass
class SignalEvent:
    symbol: str
    direction: Literal['BUY', 'SELL']
    entry_price: float
    sl: float
    tp: float
    timeframe: str
    strategy_name: str
    timestamp: datetime
    atr: float = 0.0
    confidence: float = 1.0

@dataclass
class OrderEvent:
    order_id: str
    symbol: str
    direction: Literal['BUY', 'SELL']
    lots: float
    entry_price: float
    sl: float
    tp: float
    status: Literal['PENDING', 'FILLED', 'REJECTED', 'CANCELLED']
    timestamp: datetime
    broker: str = 'unknown'  # 'mt5' or 'ccxt'
    raw_response: Optional[dict] = None

@dataclass
class FillEvent:
    order_id: str
    symbol: str
    direction: Literal['BUY', 'SELL']
    fill_price: float
    lots: float
    sl: float
    tp: float
    pnl: Optional[float]
    timestamp: datetime

@dataclass
class ErrorEvent:
    source: str
    message: str
    traceback_str: str
    timestamp: datetime
    severity: Literal['WARNING', 'ERROR', 'CRITICAL'] = 'ERROR'

EventType = OHLCVBar | SignalEvent | OrderEvent | FillEvent | ErrorEvent
HandlerType = Callable[[EventType], Awaitable[None]]

class EventBus:
    """Async pub/sub event bus."""
    
    def __init__(self) -> None:
        self._subscribers: Dict[Type[EventType], List[HandlerType]] = defaultdict(list)
        self._queue: asyncio.Queue[EventType] = asyncio.Queue()
        self._running: bool = False
        self._task: Optional[asyncio.Task] = None

    def subscribe(self, event_type: Type[EventType], handler: HandlerType) -> None:
        """Subscribe a handler to a specific event type."""
        self._subscribers[event_type].append(handler)
        logger.debug(f"Subscribed handler {handler.__name__} to {event_type.__name__}")

    def publish(self, event: EventType) -> None:
        """Publish an event to the bus (non-blocking)."""
        try:
            self._queue.put_nowait(event)
        except asyncio.QueueFull:
            logger.error("Event queue is full, dropping event", event_type=type(event).__name__)

    async def run(self) -> None:
        """Start the event dispatch loop."""
        self._running = True
        logger.info("EventBus started")
        
        while self._running:
            try:
                event = await self._queue.get()
                await self._dispatch(event)
                self._queue.task_done()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.exception("Error in event loop", error=str(e))
                
        logger.info("EventBus stopped")

    async def _dispatch(self, event: EventType) -> None:
        """Dispatch an event to all subscribers."""
        event_type = type(event)
        handlers = self._subscribers.get(event_type, [])
        
        if not handlers:
            return
            
        tasks = [asyncio.create_task(handler(event)) for handler in handlers]
        
        results = await asyncio.gather(*tasks, return_exceptions=True)
        for handler, result in zip(handlers, results):
            if isinstance(result, Exception):
                logger.error(
                    "Error handling event", 
                    event_type=event_type.__name__, 
                    handler=handler.__name__, 
                    error=str(result)
                )

    async def stop(self) -> None:
        """Stop the event dispatch loop gracefully."""
        self._running = False
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

# Global singleton
event_bus = EventBus()
