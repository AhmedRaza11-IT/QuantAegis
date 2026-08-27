import pytest
import pandas as pd
import numpy as np
from datetime import datetime, timedelta, timezone
from quantaegis.core.config import Settings
from quantaegis.risk_engine import RiskManager


@pytest.fixture
def sample_ohlcv_df():
    """Generate 300 rows of realistic OHLCV data."""
    np.random.seed(42)
    n = 300
    close = 1900.0 + np.cumsum(np.random.randn(n) * 2.0)
    high = close + np.abs(np.random.randn(n) * 1.5) + 0.1
    low = close - np.abs(np.random.randn(n) * 1.5) - 0.1
    open_ = close + np.random.randn(n) * 0.5
    volume = np.random.randint(100, 10000, n).astype(float)
    timestamps = [
        datetime(2024, 1, 1, tzinfo=timezone.utc) + timedelta(hours=i) for i in range(n)
    ]
    df = pd.DataFrame(
        {"open": open_, "high": high, "low": low, "close": close, "volume": volume},
        index=timestamps,
    )
    return df


@pytest.fixture
def real_settings():
    """Real Settings instance loaded with default configuration."""
    return Settings.load_config("config.yaml")


@pytest.fixture
def risk_manager(real_settings):
    """Real RiskManager instance initialized with real Settings."""
    return RiskManager(real_settings)
