import asyncio
from typing import AsyncIterator, List, Dict, Optional, Tuple
import pandas as pd
from tenacity import retry, wait_exponential, stop_after_attempt
import traceback
from datetime import datetime, timezone

from quantaegis.core.events import OHLCVBar, ErrorEvent, event_bus
from quantaegis.core.logger import get_logger
from .base import BaseDataFeed

logger = get_logger(__name__)

try:
    import MetaTrader5 as mt5
except ImportError:
    logger.error("MetaTrader5 package is not installed. MT5DataFeed will not work.")
    mt5 = None

class MT5DataFeed(BaseDataFeed):
    """MetaTrader 5 data feed implementation."""
    
    _TIMEFRAME_MAP = {}
    if mt5 is not None:
        _TIMEFRAME_MAP = {
            "M1": mt5.TIMEFRAME_M1,
            "M5": mt5.TIMEFRAME_M5,
            "M15": mt5.TIMEFRAME_M15,
            "H1": mt5.TIMEFRAME_H1,
            "H4": mt5.TIMEFRAME_H4,
            "D1": mt5.TIMEFRAME_D1
        }
    
    def __init__(
        self,
        login: int,
        password: str,
        server: str,
        path: str,
        symbols: List[str],
        timeframes: List[str],
        poll_interval_seconds: int = 1
    ) -> None:
        if mt5 is None:
            raise ImportError("MetaTrader5 is required for MT5DataFeed.")
        self.login = login
        self.password = password
        self.server = server
        self.path = path
        self.symbols = symbols
        self.timeframes = timeframes
        self.poll_interval_seconds = poll_interval_seconds
        
        self._last_timestamps: Dict[Tuple[str, str], int] = {}
        self._running = False
        
    @retry(wait=wait_exponential(min=1, max=4), stop=stop_after_attempt(3), reraise=True)
    async def connect(self) -> None:
        path_info = self.path if self.path else "Default/Auto-detect"
        logger.info(f"Connecting to MT5 terminal at {path_info} (server: {self.server})")

        def _connect() -> bool:
            import os
            if self.path and os.path.exists(self.path):
                if not mt5.initialize(path=self.path):
                    return False
            else:
                if not mt5.initialize():
                    return False
            return mt5.login(login=self.login, password=self.password, server=self.server)
            
        loop = asyncio.get_event_loop()
        success = await loop.run_in_executor(None, _connect)
        
        if not success:
            error = mt5.last_error()
            msg = f"Failed to connect to MT5. Error: {error}"
            logger.error(msg)
            event_bus.publish(
                ErrorEvent(
                    source="MT5DataFeed",
                    message=msg,
                    traceback_str="",
                    timestamp=datetime.now(timezone.utc),
                )
            )
            raise ConnectionError(msg)
            
        logger.info("Successfully connected to MT5 terminal.")
        
    async def disconnect(self) -> None:
        self._running = False
        def _shutdown():
            mt5.shutdown()
            
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, _shutdown)
        logger.info("Disconnected from MT5.")
        
    async def stream(self) -> AsyncIterator[OHLCVBar]:
        self._running = True
        loop = asyncio.get_event_loop()
        
        def _fetch_latest(symbol: str, tf: str) -> Optional[Tuple[int, float, float, float, float, float]]:
            tf_const = self._TIMEFRAME_MAP.get(tf)
            if not tf_const:
                return None
            rates = mt5.copy_rates_from_pos(symbol, tf_const, 0, 1)
            if rates is None or len(rates) == 0:
                error = mt5.last_error()
                logger.error(f"Failed to fetch rates for {symbol} {tf}. Error: {error}")
                return None
            rate = rates[0]
            # time, open, high, low, close, tick_volume, spread, real_volume
            return (rate[0], rate[1], rate[2], rate[3], rate[4], float(rate[5]))
        
        while self._running:
            for symbol in self.symbols:
                for tf in self.timeframes:
                    try:
                        rate = await loop.run_in_executor(None, _fetch_latest, symbol, tf)
                        if rate:
                            timestamp, open_, high, low, close, volume = rate
                            key = (symbol, tf)
                            last_ts = self._last_timestamps.get(key)
                            
                            if last_ts is None or timestamp > last_ts:
                                self._last_timestamps[key] = timestamp
                                bar = OHLCVBar(
                                    symbol=symbol,
                                    timeframe=tf,
                                    timestamp=timestamp,
                                    open=open_,
                                    high=high,
                                    low=low,
                                    close=close,
                                    volume=volume,
                                    source="MT5"
                                )
                                logger.debug(f"New bar for {symbol} {tf}: {bar}")
                                yield bar
                    except Exception as e:
                        msg = f"Error fetching {symbol} {tf}: {str(e)}"
                        logger.error(msg)
                        event_bus.publish(ErrorEvent(source="MT5DataFeed", message=msg, exception=e))
            
            await asyncio.sleep(self.poll_interval_seconds)

    async def get_historical_ohlcv(self, symbol: str, timeframe: str, count: int) -> pd.DataFrame:
        tf_const = self._TIMEFRAME_MAP.get(timeframe)
        if not tf_const:
            raise ValueError(f"Invalid timeframe: {timeframe}")
            
        def _fetch():
            rates = mt5.copy_rates_from_pos(symbol, tf_const, 0, count)
            return rates
            
        loop = asyncio.get_event_loop()
        rates = await loop.run_in_executor(None, _fetch)
        
        if rates is None:
            error = mt5.last_error()
            msg = f"Failed to fetch historical data for {symbol} {timeframe}. Error: {error}"
            logger.error(msg)
            raise ValueError(msg)
            
        df = pd.DataFrame(rates)
        df['timestamp'] = df['time']
        df = df[['timestamp', 'open', 'high', 'low', 'close', 'tick_volume']].rename(columns={'tick_volume': 'volume'})
        return df
        
    @property
    def is_connected(self) -> bool:
        if mt5 is None:
            return False
        return mt5.terminal_info() is not None
