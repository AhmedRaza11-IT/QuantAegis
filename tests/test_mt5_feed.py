import pytest
from unittest.mock import patch, MagicMock
import numpy as np
from tenacity import stop_after_attempt
from quantaegis.data_feed.mt5_feed import MT5DataFeed


@pytest.mark.asyncio
async def test_connect_success():
    with patch("quantaegis.data_feed.mt5_feed.mt5") as mock_mt5:
        mock_mt5.initialize.return_value = True
        mock_mt5.login.return_value = True
        mock_mt5.account_info.return_value = MagicMock(login=123456)

        feed = MT5DataFeed(
            login=123456,
            password="pwd",
            server="Demo",
            path="",
            symbols=["XAUUSD"],
            timeframes=["M15"],
        )
        await feed.connect()
        assert feed.is_connected


@pytest.mark.asyncio
async def test_connect_failure_raises():
    with patch("quantaegis.data_feed.mt5_feed.mt5") as mock_mt5:
        mock_mt5.initialize.return_value = False
        mock_mt5.last_error.return_value = (1, "Failed")

        feed = MT5DataFeed(
            login=123456,
            password="pwd",
            server="Demo",
            path="",
            symbols=["XAUUSD"],
            timeframes=["M15"],
        )
        feed.connect.retry.stop = stop_after_attempt(1)
        with pytest.raises(ConnectionError):
            await feed.connect()


@pytest.mark.asyncio
async def test_get_historical_ohlcv_returns_dataframe():
    with patch("quantaegis.data_feed.mt5_feed.mt5") as mock_mt5:
        rates = np.array(
            [(1704067200, 2000.0, 2010.0, 1995.0, 2005.0, 100)],
            dtype=[
                ("time", "i8"),
                ("open", "f8"),
                ("high", "f8"),
                ("low", "f8"),
                ("close", "f8"),
                ("tick_volume", "i8"),
            ],
        )
        mock_mt5.copy_rates_from_pos.return_value = rates

        feed = MT5DataFeed(
            login=123456,
            password="pwd",
            server="Demo",
            path="",
            symbols=["XAUUSD"],
            timeframes=["M15"],
        )
        df = await feed.get_historical_ohlcv("XAUUSD", "M15", 10)
        assert not df.empty
        assert "close" in df.columns
        assert df["close"].iloc[0] == 2005.0
