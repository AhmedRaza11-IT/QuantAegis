import pytest
import pandas as pd
import numpy as np
from datetime import datetime, timezone, timedelta
from quantaegis.core.events import OHLCVBar
from quantaegis.strategies.multi_tf_trend import MultiTimeframeTrendStrategy


def create_mock_df(n=250, trend="up"):
    """Helper to generate mock OHLCV dataframe with consistent trend."""
    timestamps = [
        datetime(2024, 1, 1, tzinfo=timezone.utc) + timedelta(minutes=15 * i)
        for i in range(n)
    ]
    if trend == "up":
        close = np.linspace(100.0, 200.0, n)
    elif trend == "down":
        close = np.linspace(200.0, 100.0, n)
    else:
        close = np.full(n, 150.0)

    high = close + 1.0
    low = close - 1.0
    open_ = close - 0.2 if trend == "up" else close + 0.2
    volume = np.full(n, 1000.0)

    return pd.DataFrame(
        {"open": open_, "high": high, "low": low, "close": close, "volume": volume},
        index=timestamps,
    )


def test_insufficient_data_returns_none():
    strategy = MultiTimeframeTrendStrategy()
    df_short = create_mock_df(n=100)
    bar = OHLCVBar(
        symbol="BTCUSDT",
        timeframe="15m",
        timestamp=datetime.now(timezone.utc),
        open=150.0,
        high=151.0,
        low=149.0,
        close=150.0,
        volume=1000.0,
        source="ccxt",
    )
    sig = strategy.on_bar(bar, df_short, df_short)
    assert sig is None


def test_strategy_reset():
    strategy = MultiTimeframeTrendStrategy()
    strategy._last_signal["BTCUSDT"] = "BUY"
    strategy.reset()
    assert len(strategy._last_signal) == 0


def test_no_duplicate_signal():
    strategy = MultiTimeframeTrendStrategy()
    strategy._last_signal["BTCUSDT"] = "BUY"
    htf = create_mock_df(250, "up")
    ltf = create_mock_df(250, "up")
    bar = OHLCVBar(
        symbol="BTCUSDT",
        timeframe="15m",
        timestamp=datetime.now(timezone.utc),
        open=199.0,
        high=201.0,
        low=198.0,
        close=200.0,
        volume=1000.0,
        source="ccxt",
    )
    # If the last signal was BUY, even if conditions meet, duplicate is suppressed
    sig = strategy.on_bar(bar, htf, ltf)
    assert sig is None
