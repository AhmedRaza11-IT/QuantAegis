"""
multi_tf_trend.py — Multi-Timeframe Trend Confluence Strategy.

Signal logic:
    BUY:  HTF (close > EMA200 AND EMA50 > EMA200)
          AND HTF RSI in [rsi_oversold, rsi_overbought]
          AND LTF MACD bullish crossover
          AND LTF close > EMA50

    SELL: HTF (close < EMA200 AND EMA50 < EMA200)
          AND HTF RSI in [rsi_oversold, rsi_overbought]
          AND LTF MACD bearish crossover
          AND LTF close < EMA50

SL/TP derived from ATR with configurable multipliers.
Minimum 1.5× R:R ratio enforced.
"""
import pandas as pd
from datetime import datetime, timezone
from typing import Optional, Dict, Literal

from quantaegis.core.events import OHLCVBar, SignalEvent
from quantaegis.core.logger import get_logger
from quantaegis.core.indicators import add_all_indicators
from .base import BaseStrategy

logger = get_logger(__name__)


class MultiTimeframeTrendStrategy(BaseStrategy):
    name = "MultiTimeframeTrend"

    def __init__(self, config=None) -> None:
        from quantaegis.core.config import get_settings
        self.cfg = config if config is not None else get_settings().strategy
        self._last_signal: Dict[str, str] = {}

    def reset(self) -> None:
        self._last_signal.clear()

    def _compute_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        """Add all indicators to a copy of df using the `ta` library."""
        return add_all_indicators(
            df.copy(),
            ema_fast=self.cfg.ema_fast,
            ema_slow=self.cfg.ema_slow,
            rsi_period=self.cfg.rsi_period,
            macd_fast=self.cfg.macd_fast,
            macd_slow=self.cfg.macd_slow,
            macd_signal=self.cfg.macd_signal,
            atr_period=self.cfg.atr_period,
        )

    def _detect_macd_cross(self, df: pd.DataFrame) -> Optional[Literal["BUY", "SELL"]]:
        """Detect a MACD histogram sign change in the last two rows."""
        if len(df) < 2 or "MACD_hist" not in df.columns:
            return None

        prev = df["MACD_hist"].iloc[-2]
        last = df["MACD_hist"].iloc[-1]

        if pd.isna(prev) or pd.isna(last):
            return None

        if prev <= 0 and last > 0:
            return "BUY"
        if prev >= 0 and last < 0:
            return "SELL"
        return None

    def on_bar(
        self,
        bar: OHLCVBar,
        htf_data: pd.DataFrame,
        ltf_data: pd.DataFrame,
    ) -> Optional[SignalEvent]:
        """Evaluate the strategy on a new LTF bar. Returns SignalEvent or None."""
        if len(htf_data) < self.cfg.ema_slow or len(ltf_data) < self.cfg.ema_slow:
            logger.debug(f"{self.name}: Insufficient data for {bar.symbol}.")
            return None

        htf = self._compute_indicators(htf_data)
        ltf = self._compute_indicators(ltf_data)

        ema_fast_col = f"EMA_{self.cfg.ema_fast}"
        ema_slow_col = f"EMA_{self.cfg.ema_slow}"
        rsi_col      = f"RSI_{self.cfg.rsi_period}"
        atr_col      = f"ATR_{self.cfg.atr_period}"

        required_htf = [ema_fast_col, ema_slow_col, rsi_col]
        required_ltf = [ema_fast_col, atr_col, "MACD_hist"]

        if not all(c in htf.columns for c in required_htf):
            return None
        if not all(c in ltf.columns for c in required_ltf):
            return None

        last_htf = htf.iloc[-1]
        last_ltf = ltf.iloc[-1]

        if pd.isna(last_htf[ema_slow_col]) or pd.isna(last_ltf[ema_fast_col]):
            return None

        # ── Higher-timeframe trend filter ─────────────────────────────────────
        htf_uptrend = (
            last_htf["close"] > last_htf[ema_slow_col]
            and last_htf[ema_fast_col] > last_htf[ema_slow_col]
        )
        htf_downtrend = (
            last_htf["close"] < last_htf[ema_slow_col]
            and last_htf[ema_fast_col] < last_htf[ema_slow_col]
        )

        rsi = last_htf[rsi_col]
        valid_rsi = self.cfg.rsi_oversold <= rsi <= self.cfg.rsi_overbought

        # ── Lower-timeframe entry trigger ────────────────────────────────────
        macd_cross    = self._detect_macd_cross(ltf)
        ltf_above_ema = last_ltf["close"] > last_ltf[ema_fast_col]
        ltf_below_ema = last_ltf["close"] < last_ltf[ema_fast_col]

        signal_dir: Optional[str] = None
        if htf_uptrend and valid_rsi and macd_cross == "BUY" and ltf_above_ema:
            signal_dir = "BUY"
        elif htf_downtrend and valid_rsi and macd_cross == "SELL" and ltf_below_ema:
            signal_dir = "SELL"
        else:
            logger.debug(
                f"{self.name}: No signal for {bar.symbol} | "
                f"HTF_up={htf_uptrend} HTF_dn={htf_downtrend} "
                f"RSI={rsi:.1f} MACD_cross={macd_cross}"
            )
            return None

        # Suppress duplicate consecutive signals per symbol
        if self._last_signal.get(bar.symbol) == signal_dir:
            logger.debug(f"{self.name}: Suppressing duplicate {signal_dir} for {bar.symbol}")
            return None

        # ── SL / TP via ATR ──────────────────────────────────────────────────
        atr = last_ltf[atr_col]
        if pd.isna(atr) or atr <= 0:
            logger.debug(f"{self.name}: Invalid ATR for {bar.symbol}, skipping.")
            return None

        entry = bar.close
        if signal_dir == "BUY":
            sl = entry - atr * self.cfg.atr_sl_multiplier
            tp = entry + atr * self.cfg.atr_tp_multiplier
        else:
            sl = entry + atr * self.cfg.atr_sl_multiplier
            tp = entry - atr * self.cfg.atr_tp_multiplier

        # Enforce minimum 1.5× R:R
        sl_dist = abs(entry - sl)
        tp_dist = abs(entry - tp)
        if sl_dist > 0 and tp_dist < 1.5 * sl_dist:
            logger.debug(
                f"{self.name}: R:R too low for {bar.symbol} "
                f"(TP={tp_dist:.5f} SL={sl_dist:.5f})"
            )
            return None

        self._last_signal[bar.symbol] = signal_dir
        logger.info(
            f"{self.name}: {signal_dir} signal | {bar.symbol} "
            f"entry={entry:.5f} sl={sl:.5f} tp={tp:.5f} atr={atr:.5f}"
        )

        return SignalEvent(
            symbol=bar.symbol,
            direction=signal_dir,
            entry_price=entry,
            sl=sl,
            tp=tp,
            timeframe=bar.timeframe,
            strategy_name=self.name,
            timestamp=bar.timestamp,
            atr=atr,
            confidence=1.0,
        )
