"""
analyzer.py — Quantitative Intelligence & "Invest or Not" Decision Engine.

Analyzes multi-timeframe price action, trend alignment, momentum,
and volatility to generate institutional trade recommendations,
support/resistance levels, and confluence ratings.
"""
from typing import Dict, Any, List, Optional
import pandas as pd
import numpy as np
from datetime import datetime, timezone

from quantaegis.core.indicators import add_all_indicators
from quantaegis.core.config import get_settings


class MarketAnalyzer:
    """Quantitative decision engine providing actionable market insights."""

    def __init__(self) -> None:
        self.settings = get_settings()

    def calculate_support_resistance(self, df: pd.DataFrame, window: int = 20) -> tuple[list[float], list[float]]:
        """Identify local pivot swing highs and lows as key levels."""
        if len(df) < window:
            return [], []

        highs = df["high"].values
        lows = df["low"].values
        current_price = df["close"].iloc[-1]

        pivot_supports = []
        pivot_resistances = []

        for i in range(5, len(df) - 5):
            # Swing low
            if lows[i] == min(lows[i - 5 : i + 6]):
                if lows[i] < current_price:
                    pivot_supports.append(float(lows[i]))
            # Swing high
            if highs[i] == max(highs[i - 5 : i + 6]):
                if highs[i] > current_price:
                    pivot_resistances.append(float(highs[i]))

        # Take unique rounded levels
        supports = sorted(list(set([round(s, 2 if current_price > 100 else 5) for s in pivot_supports])))[-3:]
        resistances = sorted(list(set([round(r, 2 if current_price > 100 else 5) for r in pivot_resistances])))[:3]

        return supports, resistances

    def analyze_asset(
        self,
        symbol: str,
        ltf_df: pd.DataFrame,
        htf_df: Optional[pd.DataFrame] = None,
        macro_data: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Generate comprehensive 'Invest or Not' insights incorporating technicals & Forex Factory news.
        """
        cfg = self.settings.strategy
        ltf = add_all_indicators(
            ltf_df.copy(),
            ema_fast=cfg.ema_fast,
            ema_slow=cfg.ema_slow,
            rsi_period=cfg.rsi_period,
            macd_fast=cfg.macd_fast,
            macd_slow=cfg.macd_slow,
            macd_signal=cfg.macd_signal,
            atr_period=cfg.atr_period,
        )

        if htf_df is not None and len(htf_df) > 50:
            htf = add_all_indicators(
                htf_df.copy(),
                ema_fast=cfg.ema_fast,
                ema_slow=cfg.ema_slow,
                rsi_period=cfg.rsi_period,
                macd_fast=cfg.macd_fast,
                macd_slow=cfg.macd_slow,
                macd_signal=cfg.macd_signal,
                atr_period=cfg.atr_period,
            )
        else:
            htf = ltf.copy()

        last_ltf = ltf.iloc[-1]
        prev_ltf = ltf.iloc[-2] if len(ltf) > 1 else last_ltf
        last_htf = htf.iloc[-1]

        current_price = float(last_ltf["close"])
        ema_fast_val = float(last_ltf.get(f"EMA_{cfg.ema_fast}", current_price))
        ema_slow_val = float(last_ltf.get(f"EMA_{cfg.ema_slow}", current_price))
        htf_ema_slow = float(last_htf.get(f"EMA_{cfg.ema_slow}", current_price))
        htf_ema_fast = float(last_htf.get(f"EMA_{cfg.ema_fast}", current_price))

        rsi_val = float(last_ltf.get(f"RSI_{cfg.rsi_period}", 50.0))
        macd_hist_now = float(last_ltf.get("MACD_hist", 0.0))
        macd_hist_prev = float(prev_ltf.get("MACD_hist", 0.0))
        atr_val = float(last_ltf.get(f"ATR_{cfg.atr_period}", current_price * 0.01))

        checklist = []
        score = 0.0

        # 1. HTF Trend (Weight: 25%)
        htf_bullish = htf_ema_fast > htf_ema_slow and last_htf["close"] > htf_ema_slow
        htf_bearish = htf_ema_fast < htf_ema_slow and last_htf["close"] < htf_ema_slow
        if htf_bullish:
            score += 25.0
            checklist.append({"name": "HTF Trend Direction", "status": "BULLISH", "passed": True, "detail": "Price & EMA50 above EMA200 on Higher Timeframe"})
        elif htf_bearish:
            score -= 25.0
            checklist.append({"name": "HTF Trend Direction", "status": "BEARISH", "passed": True, "detail": "Price & EMA50 below EMA200 on Higher Timeframe"})
        else:
            checklist.append({"name": "HTF Trend Direction", "status": "NEUTRAL", "passed": False, "detail": "Trend is consolidating / sideways"})

        # 2. RSI Pullback Health (Weight: 20%)
        rsi_healthy_buy = (cfg.rsi_oversold <= rsi_val <= cfg.rsi_overbought)
        rsi_oversold = rsi_val < cfg.rsi_oversold
        rsi_overbought = rsi_val > cfg.rsi_overbought

        if rsi_healthy_buy:
            score += 20.0 if htf_bullish else -20.0
            checklist.append({"name": "RSI Momentum Zone", "status": "HEALTHY PULLBACK", "passed": True, "detail": f"RSI is at {rsi_val:.1f} (in optimal 40-60 zone)"})
        elif rsi_oversold:
            checklist.append({"name": "RSI Momentum Zone", "status": "OVERSOLD", "passed": False, "detail": f"RSI is {rsi_val:.1f} (extreme oversold, await reversal)"})
        else:
            checklist.append({"name": "RSI Momentum Zone", "status": "OVERBOUGHT", "passed": False, "detail": f"RSI is {rsi_val:.1f} (extended, risk of correction)"})

        # 3. MACD Momentum Crossover (Weight: 25%)
        macd_cross_up = macd_hist_prev <= 0 and macd_hist_now > 0
        macd_cross_down = macd_hist_prev >= 0 and macd_hist_now < 0
        macd_bullish_mom = macd_hist_now > macd_hist_prev

        if macd_cross_up:
            score += 25.0
            checklist.append({"name": "MACD Crossover", "status": "BULLISH CROSS", "passed": True, "detail": "Fresh bullish momentum crossover triggered"})
        elif macd_cross_down:
            score -= 25.0
            checklist.append({"name": "MACD Crossover", "status": "BEARISH CROSS", "passed": True, "detail": "Fresh bearish momentum crossover triggered"})
        elif macd_bullish_mom:
            score += 10.0
            checklist.append({"name": "MACD Velocity", "status": "MOMENTUM EXPANDING", "passed": True, "detail": "Histogram rising positively"})
        else:
            checklist.append({"name": "MACD Velocity", "status": "MOMENTUM FADING", "passed": False, "detail": "Histogram momentum contracting"})

        # 4. LTF EMA Confirmation (Weight: 15%)
        ltf_above_ema50 = current_price > ema_fast_val
        if ltf_above_ema50 and htf_bullish:
            score += 15.0
            checklist.append({"name": "Price vs 50 EMA", "status": "CONFIRMED", "passed": True, "detail": f"Current price ({current_price:.2f}) above 50 EMA"})
        elif not ltf_above_ema50 and htf_bearish:
            score -= 15.0
            checklist.append({"name": "Price vs 50 EMA", "status": "CONFIRMED SHORT", "passed": True, "detail": f"Current price ({current_price:.2f}) below 50 EMA"})
        else:
            checklist.append({"name": "Price vs 50 EMA", "status": "CONFLICTING", "passed": False, "detail": "Price not aligned with local 50 EMA"})

        # 5. Forex Factory Macro News Filter (Weight: 15%)
        is_news_lockdown = False
        news_lockdown_reason = None
        if macro_data:
            is_news_lockdown = macro_data.get("is_news_lockdown", False)
            news_lockdown_reason = macro_data.get("lockdown_reason")
            next_ev = macro_data.get("next_event")

            if is_news_lockdown:
                checklist.append({
                    "name": "Forex Factory Macro Filter",
                    "status": "🔴 NEWS LOCKDOWN",
                    "passed": False,
                    "detail": news_lockdown_reason or "High Impact News Imminent (< 30 mins)",
                })
            else:
                bias = macro_data.get("macro_bias", "NEUTRAL")
                checklist.append({
                    "name": "Forex Factory Macro Filter",
                    "status": "🟢 CLEAR / NORMAL",
                    "passed": True,
                    "detail": f"Macro Bias: {bias}" + (f" | Next: {next_ev['title']} ({next_ev['status']})" if next_ev else ""),
                })
                score += 15.0 if "BULLISH" in bias else (-15.0 if "BEARISH" in bias else 0.0)

        # Normalize score
        confluence_pct = int(min(100, max(0, abs(score))))

        # Verdict calculation
        if is_news_lockdown:
            verdict = "NEWS LOCKDOWN"
            verdict_color = "#f97316"  # Orange/Warning
            action = "PAUSE / AWAIT NEWS RELEASE"
            action_badge = "warning"
        elif score >= 70:
            verdict = "STRONG BUY"
            verdict_color = "#22c55e"
            action = "INVEST / BUY"
            action_badge = "bullish"
        elif score >= 35:
            verdict = "BUY"
            verdict_color = "#4ade80"
            action = "ACCUMULATE / BUY"
            action_badge = "bullish"
        elif score <= -70:
            verdict = "STRONG SELL"
            verdict_color = "#ef4444"
            action = "SHORT / EXIT"
            action_badge = "bearish"
        elif score <= -35:
            verdict = "SELL"
            verdict_color = "#f87171"
            action = "REDUCE / SELL"
            action_badge = "bearish"
        else:
            verdict = "NEUTRAL / WAIT"
            verdict_color = "#94a3b8"
            action = "DO NOT INVEST (WAIT FOR SETUP)"
            action_badge = "neutral"

        # Targets & Levels
        sl_dist = atr_val * cfg.atr_sl_multiplier
        tp1_dist = atr_val * cfg.atr_tp_multiplier
        tp2_dist = atr_val * (cfg.atr_tp_multiplier * 1.5)

        is_buy_bias = score >= 0
        if is_buy_bias:
            stop_loss = current_price - sl_dist
            take_profit_1 = current_price + tp1_dist
            take_profit_2 = current_price + tp2_dist
        else:
            stop_loss = current_price + sl_dist
            take_profit_1 = current_price - tp1_dist
            take_profit_2 = current_price - tp2_dist

        rr_ratio = round(tp1_dist / sl_dist, 2) if sl_dist > 0 else 2.0
        supports, resistances = self.calculate_support_resistance(ltf)

        # Summary narrative
        if is_news_lockdown:
            summary_text = (
                f"⚠️ HIGH-IMPACT MACRO EVENT IMMINENT: {news_lockdown_reason}. "
                f"Recommendation: Halt new market entries on {symbol} to prevent slippage during news spikes. "
                f"Resume trading 15 minutes post-release once volatility stabilizes."
            )
        elif "BUY" in verdict:
            summary_text = (
                f"High-probability BUY confluence on {symbol} (Score: {confluence_pct}%). "
                f"Technical trend and Forex Factory macro sentiment are aligned bullish. "
                f"Recommended strategy: Enter near ${current_price:,.2f} with Stop Loss at ${stop_loss:,.2f} and Target 1 at ${take_profit_1:,.2f} (1:{rr_ratio} R:R)."
            )
        elif "SELL" in verdict:
            summary_text = (
                f"Bearish continuation on {symbol} (Score: {confluence_pct}%). "
                f"Price trading below EMAs with negative momentum. "
                f"Recommended strategy: Short entry or capital protection. Stop Loss at ${stop_loss:,.2f} and downside Target at ${take_profit_1:,.2f}."
            )
        else:
            summary_text = (
                f"{symbol} is consolidating with mixed signals (Confluence: {confluence_pct}%). "
                f"Recommendation: Await confirmed breakout above ${resistances[-1] if resistances else current_price*1.01:,.2f} or below ${supports[0] if supports else current_price*0.99:,.2f}."
            )

        return {
            "symbol": symbol,
            "current_price": current_price,
            "verdict": verdict,
            "action": action,
            "action_badge": action_badge,
            "verdict_color": verdict_color,
            "confluence_score": confluence_pct,
            "summary": summary_text,
            "trade_setup": {
                "entry_price": current_price,
                "stop_loss": round(stop_loss, 2 if current_price > 100 else 5),
                "take_profit_1": round(take_profit_1, 2 if current_price > 100 else 5),
                "take_profit_2": round(take_profit_2, 2 if current_price > 100 else 5),
                "risk_reward_ratio": f"1:{rr_ratio}",
                "atr": round(atr_val, 4),
            },
            "technical_indicators": {
                "ema_50": round(ema_fast_val, 2 if current_price > 100 else 5),
                "ema_200": round(ema_slow_val, 2 if current_price > 100 else 5),
                "rsi_14": round(rsi_val, 1),
                "macd_histogram": round(macd_hist_now, 4),
                "atr_14": round(atr_val, 4),
            },
            "key_levels": {
                "supports": supports,
                "resistances": resistances,
            },
            "checklist": checklist,
            "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC"),
        }
