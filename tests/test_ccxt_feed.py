import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from quantaegis.data_feed.ccxt_feed import CCXTDataFeed
from tenacity import stop_after_attempt


@pytest.mark.asyncio
async def test_connect_success():
    with patch("quantaegis.data_feed.ccxt_feed.ccxtpro") as mock_ccxtpro:
        mock_exchange = MagicMock()
        mock_exchange.load_markets = AsyncMock(return_value={"BTC/USDT": {}})
        getattr(mock_ccxtpro, "binance").return_value = mock_exchange

        feed = CCXTDataFeed(
            exchange_id="binance",
            api_key="key",
            secret="sec",
            symbols=["BTC/USDT"],
            timeframes=["15m"],
        )
        await feed.connect()
        assert feed.is_connected


@pytest.mark.asyncio
async def test_connect_failure_raises():
    with patch("quantaegis.data_feed.ccxt_feed.ccxtpro") as mock_ccxtpro:
        mock_exchange = MagicMock()
        mock_exchange.load_markets = AsyncMock(side_effect=RuntimeError("Auth error"))
        getattr(mock_ccxtpro, "binance").return_value = mock_exchange

        feed = CCXTDataFeed(
            exchange_id="binance",
            api_key="key",
            secret="sec",
            symbols=["BTC/USDT"],
            timeframes=["15m"],
        )
        with pytest.raises(RuntimeError):
            await feed.connect()


@pytest.mark.asyncio
async def test_get_historical_ohlcv_returns_dataframe():
    with patch("quantaegis.data_feed.ccxt_feed.ccxtpro") as mock_ccxtpro:
        mock_exchange = MagicMock()
        mock_exchange.load_markets = AsyncMock(return_value={})
        mock_exchange.fetch_ohlcv = AsyncMock(
            return_value=[
                [1704067200000, 42000.0, 42500.0, 41800.0, 42300.0, 150.0]
            ]
        )
        getattr(mock_ccxtpro, "binance").return_value = mock_exchange

        feed = CCXTDataFeed(
            exchange_id="binance",
            api_key="key",
            secret="sec",
            symbols=["BTC/USDT"],
            timeframes=["15m"],
        )
        await feed.connect()
        df = await feed.get_historical_ohlcv("BTC/USDT", "15m", 10)
        assert not df.empty
        assert "close" in df.columns
        assert df["close"].iloc[0] == 42300.0
