"""
indicators.py — Unified technical indicator calculations.

Uses the `ta` library (Python 3.14 compatible) as a drop-in replacement
for pandas-ta. Returns Series with standard column names expected
by the strategy layer.
"""
from typing import Optional
import pandas as pd
import ta


def compute_ema(series: pd.Series, period: int) -> pd.Series:
    """Exponential Moving Average."""
    return ta.trend.EMAIndicator(close=series, window=period).ema_indicator()


def compute_rsi(series: pd.Series, period: int) -> pd.Series:
    """Relative Strength Index."""
    return ta.momentum.RSIIndicator(close=series, window=period).rsi()


def compute_macd(
    series: pd.Series,
    fast: int = 12,
    slow: int = 26,
    signal: int = 9,
) -> tuple[pd.Series, pd.Series, pd.Series]:
    """
    MACD indicator.
    Returns: (macd_line, signal_line, macd_histogram)
    """
    macd = ta.trend.MACD(close=series, window_fast=fast, window_slow=slow, window_sign=signal)
    return macd.macd(), macd.macd_signal(), macd.macd_diff()


def compute_atr(
    high: pd.Series,
    low: pd.Series,
    close: pd.Series,
    period: int = 14,
) -> pd.Series:
    """Average True Range."""
    return ta.volatility.AverageTrueRange(
        high=high, low=low, close=close, window=period
    ).average_true_range()


def add_all_indicators(
    df: pd.DataFrame,
    ema_fast: int = 50,
    ema_slow: int = 200,
    rsi_period: int = 14,
    macd_fast: int = 12,
    macd_slow: int = 26,
    macd_signal: int = 9,
    atr_period: int = 14,
) -> pd.DataFrame:
    """
    Add all required indicators to a DataFrame in-place.

    Expects columns: open, high, low, close, volume
    Adds columns:
        EMA_{ema_fast}, EMA_{ema_slow},
        RSI_{rsi_period},
        MACD_line, MACD_signal, MACD_hist,
        ATR_{atr_period}
    """
    if len(df) < max(ema_slow, rsi_period, macd_slow, atr_period):
        return df

    close = df["close"]
    df[f"EMA_{ema_fast}"]   = compute_ema(close, ema_fast)
    df[f"EMA_{ema_slow}"]   = compute_ema(close, ema_slow)
    df[f"RSI_{rsi_period}"] = compute_rsi(close, rsi_period)

    macd_l, macd_s, macd_h = compute_macd(close, macd_fast, macd_slow, macd_signal)
    df["MACD_line"]   = macd_l
    df["MACD_signal"] = macd_s
    df["MACD_hist"]   = macd_h

    df[f"ATR_{atr_period}"] = compute_atr(df["high"], df["low"], close, atr_period)

    return df
