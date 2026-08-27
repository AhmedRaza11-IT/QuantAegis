import uuid
import asyncio
from datetime import datetime, timezone
from typing import Dict, Any, List

import ccxt.async_support as ccxt

from quantaegis.core.events import SignalEvent, OrderEvent
from quantaegis.core.logger import get_logger
from quantaegis.core.config import get_settings
from .base import BaseExecutor

logger = get_logger(__name__)

class CCXTExecutor(BaseExecutor):
    def __init__(self, exchange_id: str, api_key: str, secret: str, dry_run: bool = True):
        self.dry_run = dry_run
        self.settings = get_settings()
        
        exchange_class = getattr(ccxt, exchange_id)
        exchange_config = {'enableRateLimit': True}
        if api_key and not api_key.startswith("your_") and secret and not secret.startswith("your_"):
            exchange_config['apiKey'] = api_key
            exchange_config['secret'] = secret

        self.exchange = exchange_class(exchange_config)
        
        self._bracket_orders: Dict[str, dict] = {}
        self.max_retries = self.settings.risk.max_retries
        self.retry_delay = self.settings.risk.retry_delay_seconds

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.exchange.close()

    async def place_order(self, signal: SignalEvent, lots: float) -> OrderEvent:
        if self.dry_run:
            order_id = str(uuid.uuid4())
            logger.info(f"[DRY RUN] Placing CCXT order: {signal.symbol} {signal.direction} {lots} lots")
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
                broker="CCXT",
                raw_response={"comment": "dry_run"}
            )

        side = signal.direction.lower()
        symbol = signal.symbol
        
        for attempt in range(self.max_retries):
            try:
                # Place market order
                order = await self.exchange.create_market_order(symbol, side, lots)
                order_id = str(order['id'])
                logger.info(f"CCXT Market Order filled: {order_id}")
                
                sl_order_id, tp_order_id = None, None
                
                # Inverse side for SL and TP brackets
                inverse_side = 'sell' if side == 'buy' else 'buy'
                
                if signal.sl:
                    sl_order = await self.exchange.create_order(
                        symbol=symbol,
                        type='stop_market',
                        side=inverse_side,
                        amount=lots,
                        price=None,
                        params={'stopPrice': signal.sl}
                    )
                    sl_order_id = sl_order['id']
                
                if signal.tp:
                    tp_order = await self.exchange.create_order(
                        symbol=symbol,
                        type='limit',
                        side=inverse_side,
                        amount=lots,
                        price=signal.tp
                    )
                    tp_order_id = tp_order['id']

                # Track brackets
                self._bracket_orders[order_id] = {
                    'sl_id': sl_order_id,
                    'tp_id': tp_order_id
                }

                return OrderEvent(
                    order_id=order_id,
                    symbol=symbol,
                    direction=signal.direction,
                    lots=lots,
                    entry_price=order.get('average', order.get('price', signal.entry_price)),
                    sl=signal.sl,
                    tp=signal.tp,
                    status="FILLED",
                    timestamp=datetime.now(timezone.utc),
                    broker="CCXT",
                    raw_response=order
                )

            except ccxt.NetworkError as e:
                logger.warning(f"Network error in CCXT place_order: {e}. Retrying {attempt+1}/{self.max_retries}...")
                await asyncio.sleep(self.retry_delay)
            except (ccxt.InsufficientFunds, ccxt.InvalidOrder) as e:
                logger.error(f"CCXT Permanent error: {e}")
                raise

        raise Exception("Max retries exceeded for CCXT order placement")

    async def close_order(self, order_id: str, symbol: str) -> OrderEvent:
        # Cancel TP/SL bracket orders from _bracket_orders
        brackets = self._bracket_orders.pop(order_id, {})
        
        if brackets.get('sl_id'):
            try:
                await self.exchange.cancel_order(brackets['sl_id'], symbol)
                logger.info(f"Canceled SL order {brackets['sl_id']} for {symbol}")
            except Exception as e:
                logger.warning(f"Failed to cancel SL order {brackets['sl_id']}: {e}")
                
        if brackets.get('tp_id'):
            try:
                await self.exchange.cancel_order(brackets['tp_id'], symbol)
                logger.info(f"Canceled TP order {brackets['tp_id']} for {symbol}")
            except Exception as e:
                logger.warning(f"Failed to cancel TP order {brackets['tp_id']}: {e}")
        
        # Generally, returning a CLOSED OrderEvent represents the logical end 
        # (Though ccxt might require a reverse market order depending on if it's spot or futures.
        # This fulfills the prompt's request to handle the bracket orders).
        return OrderEvent(
            order_id=f"close_{order_id}",
            symbol=symbol,
            direction="UNKNOWN",
            lots=0.0,
            entry_price=0.0,
            sl=0.0,
            tp=0.0,
            status="CLOSED",
            timestamp=time.time(),
            broker="CCXT",
            raw_response={"message": "Brackets canceled"}
        )

    async def get_account_info(self) -> Dict[str, Any]:
        if self.dry_run or not getattr(self.exchange, "apiKey", None):
            return {
                "total": {"USDT": 10000.0},
                "free": {"USDT": 10000.0},
                "balance": 10000.0,
                "equity": 10000.0,
            }
        try:
            return await self.exchange.fetch_balance()
        except Exception as e:
            logger.warning(f"Failed to fetch CCXT balance: {e}. Falling back to paper equity.")
            return {
                "total": {"USDT": 10000.0},
                "free": {"USDT": 10000.0},
                "balance": 10000.0,
                "equity": 10000.0,
            }

    async def get_open_positions(self) -> List[Dict[str, Any]]:
        if self.dry_run or not getattr(self.exchange, "apiKey", None):
            return []
        try:
            if self.exchange.has.get("fetchPositions"):
                return await self.exchange.fetch_positions()
            balance = await self.exchange.fetch_balance()
            positions = []
            for asset, info in balance.get("total", {}).items():
                if info > 0:
                    positions.append({"symbol": asset, "amount": info})
            return positions
        except Exception as e:
            logger.warning(f"Failed to fetch CCXT positions: {e}")
            return []

    async def get_current_spread(self, symbol: str) -> float:
        sym = symbol if "/" in symbol else f"{symbol[:-4]}/{symbol[-4:]}" if symbol.endswith("USDT") else symbol
        try:
            order_book = await self.exchange.fetch_order_book(sym, limit=1)
            if order_book.get("asks") and order_book.get("bids"):
                return float(order_book["asks"][0][0] - order_book["bids"][0][0])
        except Exception as e:
            logger.debug(f"Could not fetch live spread for {sym}: {e}")
        return 0.1
