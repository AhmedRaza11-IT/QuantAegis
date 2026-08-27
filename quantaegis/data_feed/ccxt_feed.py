import asyncio
from typing import AsyncIterator, List, Dict, Tuple, Optional
from datetime import datetime, timezone
import traceback
import pandas as pd
from tenacity import retry, wait_exponential, stop_after_attempt, retry_if_exception_type

import ccxt.pro as ccxtpro
import ccxt

from quantaegis.core.events import OHLCVBar, ErrorEvent, event_bus
from quantaegis.core.logger import get_logger
from .base import BaseDataFeed

logger = get_logger(__name__)

class CCXTDataFeed(BaseDataFeed):
    """CCXT Pro async WebSocket data feed implementation."""
    
    def __init__(
        self,
        exchange_id: str,
        api_key: str,
        secret: str,
        symbols: List[str],
        timeframes: List[str]
    ) -> None:
        self.exchange_id = exchange_id
        # Normalize symbol names for CCXT: BTCUSDT -> BTC/USDT if needed
        self.symbols = [
            s if "/" in s else f"{s[:-4]}/{s[-4:]}" if s.endswith("USDT") else s
            for s in symbols
        ]
        self.timeframes = timeframes
        
        exchange_class = getattr(ccxtpro, exchange_id, None)
        if not exchange_class:
            raise ValueError(f"Exchange {exchange_id} is not supported by ccxt.pro")
            
        exchange_config = {'enableRateLimit': True}
        if api_key and not api_key.startswith("your_") and secret and not secret.startswith("your_"):
            exchange_config['apiKey'] = api_key
            exchange_config['secret'] = secret

        self.exchange = exchange_class(exchange_config)
        self._last_timestamps: Dict[Tuple[str, str], int] = {}
        self._running = False
        
    @retry(
        wait=wait_exponential(min=1, max=60),
        stop=stop_after_attempt(10),
        retry=retry_if_exception_type((ccxt.NetworkError, ccxt.ExchangeNotAvailable, ccxt.RateLimitExceeded)),
        reraise=True,
    )
    async def connect(self) -> None:
        logger.info(f"Connecting to {self.exchange_id}")
        try:
            await self.exchange.load_markets()
            logger.info(f"Successfully connected to {self.exchange_id}")
        except Exception as e:
            logger.error(f"Failed to connect to {self.exchange_id}: {str(e)}")
            event_bus.publish(
                ErrorEvent(
                    source="CCXTDataFeed",
                    message=str(e),
                    traceback_str=traceback.format_exc(),
                    timestamp=datetime.now(timezone.utc),
                )
            )
            raise

    async def disconnect(self) -> None:
        self._running = False
        await self.exchange.close()
        logger.info(f"Disconnected from {self.exchange_id}")

    async def _watch_symbol_timeframe(self, symbol: str, tf: str) -> AsyncIterator[OHLCVBar]:
        while self._running:
            try:
                # ccxt.pro watch_ohlcv returns a list of candles
                candles = await self.exchange.watch_ohlcv(symbol, tf)
                for candle in candles:
                    # candle: [timestamp, open, high, low, close, volume]
                    timestamp, open_, high, low, close, volume = candle
                    key = (symbol, tf)
                    last_ts = self._last_timestamps.get(key)
                    
                    if last_ts is None or timestamp > last_ts:
                        self._last_timestamps[key] = timestamp
                        dt = datetime.fromtimestamp(timestamp / 1000.0, tz=timezone.utc)
                        bar = OHLCVBar(
                            symbol=symbol,
                            timeframe=tf,
                            timestamp=dt,
                            open=float(open_),
                            high=float(high),
                            low=float(low),
                            close=float(close),
                            volume=float(volume),
                            source=self.exchange_id,
                        )
                        logger.debug(f"New bar for {symbol} {tf}: {bar}")
                        yield bar
            except Exception as e:
                logger.error(f"Error watching {symbol} {tf}: {str(e)}")
                event_bus.publish(
                    ErrorEvent(
                        source="CCXTDataFeed",
                        message=str(e),
                        traceback_str=traceback.format_exc(),
                        timestamp=datetime.now(timezone.utc),
                    )
                )
                await asyncio.sleep(5)  # Backoff before reconnecting to the stream

    async def stream(self) -> AsyncIterator[OHLCVBar]:
        self._running = True
        
        # Multiplexing async generators using an asyncio.Queue
        queue = asyncio.Queue()
        
        async def _producer(symbol: str, tf: str):
            async for bar in self._watch_symbol_timeframe(symbol, tf):
                await queue.put(bar)
                
        tasks = []
        for symbol in self.symbols:
            for tf in self.timeframes:
                task = asyncio.create_task(_producer(symbol, tf))
                tasks.append(task)
                
        try:
            while self._running:
                bar = await queue.get()
                yield bar
        finally:
            for t in tasks:
                t.cancel()

    @retry(
        wait=wait_exponential(min=1, max=60),
        stop=stop_after_attempt(10),
        retry=retry_if_exception_type((ccxt.NetworkError, ccxt.ExchangeNotAvailable, ccxt.RateLimitExceeded))
    )
    async def get_historical_ohlcv(self, symbol: str, timeframe: str, count: int) -> pd.DataFrame:
        try:
            ohlcv = await self.exchange.fetch_ohlcv(symbol, timeframe, limit=count)
            df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
            return df
        except Exception as e:
            logger.error(f"Error fetching historical data for {symbol} {timeframe}: {str(e)}")
            raise

    @property
    def is_connected(self) -> bool:
        return bool(self.exchange.markets)
