import uuid
import asyncio
from datetime import datetime, timezone
from typing import Dict, Any, List

try:
    import MetaTrader5 as mt5
except ImportError:
    mt5 = None

from quantaegis.core.events import SignalEvent, OrderEvent
from quantaegis.core.logger import get_logger
from quantaegis.core.config import get_settings
from .base import BaseExecutor

logger = get_logger(__name__)

class OrderRejectedError(Exception):
    pass

class MT5Executor(BaseExecutor):
    def __init__(self, settings=None):
        self.settings = settings or get_settings()
        self.dry_run = self.settings.app.dry_run
        self.max_retries = self.settings.risk.max_retries
        self.retry_delay = self.settings.risk.retry_delay_seconds
        
        if not mt5:
            logger.error("MetaTrader5 package is not installed.")

    async def _run_in_executor(self, func, *args, **kwargs):
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, lambda: func(*args, **kwargs))

    async def place_order(self, signal: SignalEvent, lots: float) -> OrderEvent:
        if self.dry_run:
            order_id = str(uuid.uuid4())
            logger.info(f"[DRY RUN] Placing MT5 order: {signal.symbol} {signal.direction} {lots} lots")
            return OrderEvent(
                order_id=order_id,
                symbol=signal.symbol,
                direction=signal.direction,
                lots=lots,
                entry_price=signal.entry_price,
                sl=signal.sl,
                tp=signal.tp,
                status="FILLED",
                timestamp=datetime.now(timezone.utc),
                broker="MT5",
                raw_response={"comment": "dry_run"}
            )

        if not mt5:
            raise OrderRejectedError("MT5 is not available.")

        order_type = mt5.ORDER_TYPE_BUY if signal.direction.upper() == "BUY" else mt5.ORDER_TYPE_SELL
        
        request = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": signal.symbol,
            "volume": float(lots),
            "type": order_type,
            "price": signal.entry_price,
            "sl": signal.sl,
            "tp": signal.tp,
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": mt5.ORDER_FILLING_IOC,
            "comment": "QuantAegis",
        }

        for attempt in range(self.max_retries):
            result = await self._run_in_executor(mt5.order_send, request)
            
            if result is None:
                raise OrderRejectedError("MT5 order_send returned None. Ensure MT5 is connected.")

            if result.retcode == mt5.TRADE_RETCODE_DONE:
                logger.info(f"MT5 order filled: {result.order}")
                return OrderEvent(
                    order_id=str(result.order),
                    symbol=signal.symbol,
                    direction=signal.direction,
                    lots=lots,
                    entry_price=result.price,
                    sl=signal.sl,
                    tp=signal.tp,
                    status="FILLED",
                    timestamp=datetime.now(timezone.utc),
                    broker="MT5",
                    raw_response=result._asdict() if hasattr(result, "_asdict") else str(result)
                )
            
            # Transient errors: 10004 (REQUOTE), 10018 (MARKET_CLOSED - could be momentary disconnect)
            if result.retcode in (10004, 10018):
                logger.warning(f"Transient error placing MT5 order (code {result.retcode}). Retrying {attempt+1}/{self.max_retries}...")
                await asyncio.sleep(self.retry_delay)
                continue
            else:
                logger.error(f"Permanent error placing MT5 order: {result.retcode}, {result.comment}")
                raise OrderRejectedError(f"MT5 order rejected: {result.retcode} - {result.comment}")

        raise OrderRejectedError("Max retries exceeded for MT5 order placement")

    async def close_order(self, order_id: str, symbol: str) -> OrderEvent:
        if not mt5:
            raise OrderRejectedError("MT5 is not available.")
            
        positions = await self._run_in_executor(mt5.positions_get, ticket=int(order_id))
        if not positions:
            raise OrderRejectedError(f"Position {order_id} not found to close.")
        
        position = positions[0]
        close_type = mt5.ORDER_TYPE_SELL if position.type == mt5.ORDER_TYPE_BUY else mt5.ORDER_TYPE_BUY
        tick = await self._run_in_executor(mt5.symbol_info_tick, symbol)
        
        if tick is None:
            raise OrderRejectedError(f"Failed to get tick data for {symbol}")
            
        close_price = tick.bid if close_type == mt5.ORDER_TYPE_SELL else tick.ask

        request = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": symbol,
            "volume": position.volume,
            "type": close_type,
            "position": position.ticket,
            "price": close_price,
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": mt5.ORDER_FILLING_IOC,
            "comment": "QuantAegis Close",
        }
        
        result = await self._run_in_executor(mt5.order_send, request)
        if result is None or result.retcode != mt5.TRADE_RETCODE_DONE:
            raise OrderRejectedError(f"Failed to close MT5 position: {result.retcode if result else 'None'}")
            
        return OrderEvent(
            order_id=str(result.order),
            symbol=symbol,
            direction="SELL" if close_type == mt5.ORDER_TYPE_SELL else "BUY",
            lots=position.volume,
            entry_price=result.price,
            sl=0.0,
            tp=0.0,
            status="CLOSED",
            timestamp=datetime.now(timezone.utc),
            broker="MT5",
            raw_response=result._asdict() if hasattr(result, "_asdict") else str(result)
        )

    async def get_account_info(self) -> Dict[str, Any]:
        if not mt5:
            return {"balance": 10000.0, "equity": 10000.0, "margin": 0.0, "free_margin": 10000.0}
        account = await self._run_in_executor(mt5.account_info)
        if account is None:
            return {"balance": 10000.0, "equity": 10000.0, "margin": 0.0, "free_margin": 10000.0}
        return {
            "balance": getattr(account, "balance", 10000.0),
            "equity": getattr(account, "equity", 10000.0),
            "margin": getattr(account, "margin", 0.0),
            "free_margin": getattr(account, "margin_free", 10000.0),
        }

    async def get_open_positions(self) -> List[Dict[str, Any]]:
        if not mt5:
            return []
        positions = await self._run_in_executor(mt5.positions_get)
        if not positions:
            return []
        return [p._asdict() if hasattr(p, "_asdict") else str(p) for p in positions]

    async def get_current_spread(self, symbol: str) -> float:
        if not mt5:
            return 0.0
        tick = await self._run_in_executor(mt5.symbol_info_tick, symbol)
        if tick is None:
            return 0.0
        return float(tick.ask - tick.bid)
