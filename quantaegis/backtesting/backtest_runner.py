import os
import argparse
from datetime import datetime
import pandas as pd
import numpy as np

try:
    import MetaTrader5 as mt5
except ImportError:
    mt5 = None

from quantaegis.core.config import get_settings
from quantaegis.core.logger import get_logger
from quantaegis.core.indicators import add_all_indicators


class BacktestRunner:
    """
    Backtesting engine for the MultiTimeframeTrendStrategy.
    Computes indicators, executes trades with ATR-based SL/TP,
    and calculates institutional performance metrics.
    """

    def __init__(self, config_path: str = "config.yaml") -> None:
        self.settings = get_settings()
        self.logger = get_logger("backtest_runner")

    def load_data_from_csv(self, filepath: str, symbol: str) -> pd.DataFrame:
        self.logger.info(f"Loading data from CSV: {filepath}")
        df = pd.read_csv(filepath)
        df.columns = [col.lower().strip() for col in df.columns]

        time_cols = [c for c in df.columns if "time" in c or "date" in c]
        if time_cols:
            df["timestamp"] = pd.to_datetime(df[time_cols[0]])
            df.set_index("timestamp", inplace=True)
        elif not isinstance(df.index, pd.DatetimeIndex):
            df.index = pd.date_range("2024-01-01", periods=len(df), freq="15min")

        return df

    def load_data_from_mt5(
        self, symbol: str, timeframe: str, start_date: datetime, end_date: datetime
    ) -> pd.DataFrame:
        if mt5 is None:
            self.logger.error("MetaTrader5 is not installed.")
            return pd.DataFrame()

        self.logger.info(f"Fetching MT5 data for {symbol} ({timeframe})")
        if not mt5.initialize():
            self.logger.error("MT5 initialization failed")
            return pd.DataFrame()

        tf_map = {
            "M1": mt5.TIMEFRAME_M1,
            "M5": mt5.TIMEFRAME_M5,
            "M15": mt5.TIMEFRAME_M15,
            "M30": mt5.TIMEFRAME_M30,
            "H1": mt5.TIMEFRAME_H1,
            "H4": mt5.TIMEFRAME_H4,
            "D1": mt5.TIMEFRAME_D1,
        }
        mt5_tf = tf_map.get(timeframe, mt5.TIMEFRAME_H1)

        rates = mt5.copy_rates_range(symbol, mt5_tf, start_date, end_date)
        mt5.shutdown()

        if rates is None or len(rates) == 0:
            self.logger.error(f"No MT5 data found for {symbol}")
            return pd.DataFrame()

        df = pd.DataFrame(rates)
        df["time"] = pd.to_datetime(df["time"], unit="s")
        df.set_index("time", inplace=True)
        df.rename(columns={"tick_volume": "volume"}, inplace=True)
        return df

    def compute_signals(self, htf_df: pd.DataFrame, ltf_df: pd.DataFrame) -> pd.DataFrame:
        htf = htf_df.copy()
        ltf = ltf_df.copy()

        cfg = self.settings.strategy
        htf = add_all_indicators(
            htf,
            ema_fast=cfg.ema_fast,
            ema_slow=cfg.ema_slow,
            rsi_period=cfg.rsi_period,
            macd_fast=cfg.macd_fast,
            macd_slow=cfg.macd_slow,
            macd_signal=cfg.macd_signal,
            atr_period=cfg.atr_period,
        )
        ltf = add_all_indicators(
            ltf,
            ema_fast=cfg.ema_fast,
            ema_slow=cfg.ema_slow,
            rsi_period=cfg.rsi_period,
            macd_fast=cfg.macd_fast,
            macd_slow=cfg.macd_slow,
            macd_signal=cfg.macd_signal,
            atr_period=cfg.atr_period,
        )

        aligned_htf = htf.reindex(ltf.index, method="ffill")

        ema_fast_col = f"EMA_{cfg.ema_fast}"
        ema_slow_col = f"EMA_{cfg.ema_slow}"
        rsi_col = f"RSI_{cfg.rsi_period}"
        atr_col = f"ATR_{cfg.atr_period}"

        uptrend = (aligned_htf["close"] > aligned_htf[ema_slow_col]) & (
            aligned_htf[ema_fast_col] > aligned_htf[ema_slow_col]
        )
        downtrend = (aligned_htf["close"] < aligned_htf[ema_slow_col]) & (
            aligned_htf[ema_fast_col] < aligned_htf[ema_slow_col]
        )

        rsi = aligned_htf[rsi_col]
        rsi_valid = (rsi >= cfg.rsi_oversold) & (rsi <= cfg.rsi_overbought)

        macd_hist = ltf["MACD_hist"]
        macd_cross_up = (macd_hist > 0) & (macd_hist.shift(1) <= 0)
        macd_cross_down = (macd_hist < 0) & (macd_hist.shift(1) >= 0)

        ltf_above_ema = ltf["close"] > ltf[ema_fast_col]
        ltf_below_ema = ltf["close"] < ltf[ema_fast_col]

        entries_long = uptrend & rsi_valid & macd_cross_up & ltf_above_ema
        entries_short = downtrend & rsi_valid & macd_cross_down & ltf_below_ema

        signals = pd.DataFrame(index=ltf.index)
        signals["close"] = ltf["close"]
        signals["entries_long"] = entries_long
        signals["entries_short"] = entries_short
        signals["atr"] = ltf[atr_col]
        return signals

    def run_backtest(
        self,
        symbol: str,
        htf_data: pd.DataFrame,
        ltf_data: pd.DataFrame,
        initial_cash: float = 10000.0,
        risk_pct: float = 0.01,
    ) -> tuple[dict, pd.DataFrame]:
        self.logger.info(f"Running backtest for {symbol}")
        signals = self.compute_signals(htf_data, ltf_data)
        cfg = self.settings.strategy

        cash = initial_cash
        equity_curve = []
        trades = []

        position = 0  # 1 for long, -1 for short, 0 flat
        entry_price = 0.0
        sl_price = 0.0
        tp_price = 0.0
        position_units = 0.0
        entry_time = None

        for timestamp, row in signals.iterrows():
            price = row["close"]
            atr = row["atr"]

            if position != 0:
                closed = False
                pnl = 0.0
                exit_reason = ""

                if position == 1:
                    if price <= sl_price:
                        pnl = (sl_price - entry_price) * position_units
                        closed = True
                        exit_reason = "SL"
                    elif price >= tp_price:
                        pnl = (tp_price - entry_price) * position_units
                        closed = True
                        exit_reason = "TP"
                elif position == -1:
                    if price >= sl_price:
                        pnl = (entry_price - sl_price) * position_units
                        closed = True
                        exit_reason = "SL"
                    elif price <= tp_price:
                        pnl = (entry_price - tp_price) * position_units
                        closed = True
                        exit_reason = "TP"

                if closed:
                    cash += pnl
                    trades.append(
                        {
                            "entry_time": entry_time,
                            "exit_time": timestamp,
                            "side": "BUY" if position == 1 else "SELL",
                            "pnl": pnl,
                            "pnl_pct": (pnl / (entry_price * position_units)) * 100
                            if entry_price * position_units > 0
                            else 0,
                            "reason": exit_reason,
                        }
                    )
                    position = 0

            # New Entry
            if position == 0 and pd.notna(atr) and atr > 0:
                if row["entries_long"]:
                    position = 1
                    entry_price = price
                    sl_price = entry_price - atr * cfg.atr_sl_multiplier
                    tp_price = entry_price + atr * cfg.atr_tp_multiplier
                    risk_amount = cash * risk_pct
                    sl_dist = abs(entry_price - sl_price)
                    position_units = risk_amount / sl_dist if sl_dist > 0 else 0
                    entry_time = timestamp
                elif row["entries_short"]:
                    position = -1
                    entry_price = price
                    sl_price = entry_price + atr * cfg.atr_sl_multiplier
                    tp_price = entry_price - atr * cfg.atr_tp_multiplier
                    risk_amount = cash * risk_pct
                    sl_dist = abs(entry_price - sl_price)
                    position_units = risk_amount / sl_dist if sl_dist > 0 else 0
                    entry_time = timestamp

            equity_curve.append(
                {
                    "timestamp": timestamp,
                    "equity": cash
                    + (
                        (price - entry_price) * position_units * position
                        if position != 0
                        else 0
                    ),
                }
            )

        eq_df = pd.DataFrame(equity_curve).set_index("timestamp")

        # Metrics calculation
        total_trades = len(trades)
        wins = [t for t in trades if t["pnl"] > 0]
        losses = [t for t in trades if t["pnl"] < 0]
        win_rate = (len(wins) / total_trades * 100) if total_trades > 0 else 0.0

        gross_profit = sum(t["pnl"] for t in wins)
        gross_loss = abs(sum(t["pnl"] for t in losses))
        profit_factor = (gross_profit / gross_loss) if gross_loss > 0 else 0.0

        final_equity = eq_df["equity"].iloc[-1] if not eq_df.empty else initial_cash
        total_return_pct = ((final_equity - initial_cash) / initial_cash) * 100

        # Drawdown
        eq_df["peak"] = eq_df["equity"].cummax()
        eq_df["drawdown"] = (eq_df["peak"] - eq_df["equity"]) / eq_df["peak"]
        max_drawdown_pct = eq_df["drawdown"].max() * 100 if not eq_df.empty else 0.0

        # Sharpe & Calmar
        returns = eq_df["equity"].pct_change().dropna()
        sharpe_ratio = (
            (returns.mean() / returns.std() * np.sqrt(252 * 24 * 4))
            if len(returns) > 1 and returns.std() > 0
            else 0.0
        )
        calmar_ratio = (
            (total_return_pct / max_drawdown_pct) if max_drawdown_pct > 0 else 0.0
        )

        metrics = {
            "symbol": symbol,
            "total_return_pct": total_return_pct,
            "sharpe_ratio": float(sharpe_ratio),
            "calmar_ratio": float(calmar_ratio),
            "max_drawdown_pct": float(max_drawdown_pct),
            "win_rate": float(win_rate),
            "profit_factor": float(profit_factor),
            "total_trades": total_trades,
            "best_trade_pct": max([t["pnl_pct"] for t in trades], default=0.0),
            "worst_trade_pct": min([t["pnl_pct"] for t in trades], default=0.0),
        }

        return metrics, eq_df

    def generate_report(
        self, metrics: dict, eq_df: pd.DataFrame, output_dir: str = "./reports"
    ) -> str:
        os.makedirs(output_dir, exist_ok=True)
        symbol = metrics["symbol"]
        timestamp_str = datetime.now().strftime("%Y%m%d_%H%M%S")
        report_path = os.path.join(output_dir, f"{symbol}_report_{timestamp_str}.html")

        # HTML summary
        html_content = f"""<!DOCTYPE html>
<html>
<head>
    <title>QuantAegis Backtest Report - {symbol}</title>
    <style>
        body {{ font-family: Arial, sans-serif; margin: 40px; background: #0f172a; color: #f8fafc; }}
        h1 {{ color: #38bdf8; }}
        table {{ border-collapse: collapse; width: 500px; margin-top: 20px; }}
        th, td {{ padding: 12px; text-align: left; border-bottom: 1px solid #334155; }}
        th {{ background: #1e293b; color: #94a3b8; }}
        .positive {{ color: #4ade80; }}
        .negative {{ color: #f87171; }}
    </style>
</head>
<body>
    <h1>QuantAegis Backtest Report: {symbol}</h1>
    <table>
        <tr><th>Metric</th><th>Value</th></tr>
        <tr><td>Total Return</td><td class="{'positive' if metrics['total_return_pct'] >= 0 else 'negative'}">{metrics['total_return_pct']:.2f}%</td></tr>
        <tr><td>Win Rate</td><td>{metrics['win_rate']:.2f}%</td></tr>
        <tr><td>Profit Factor</td><td>{metrics['profit_factor']:.2f}</td></tr>
        <tr><td>Max Drawdown</td><td class="negative">{metrics['max_drawdown_pct']:.2f}%</td></tr>
        <tr><td>Sharpe Ratio</td><td>{metrics['sharpe_ratio']:.2f}</td></tr>
        <tr><td>Calmar Ratio</td><td>{metrics['calmar_ratio']:.2f}</td></tr>
        <tr><td>Total Trades</td><td>{metrics['total_trades']}</td></tr>
        <tr><td>Best Trade</td><td class="positive">{metrics['best_trade_pct']:.2f}%</td></tr>
        <tr><td>Worst Trade</td><td class="negative">{metrics['worst_trade_pct']:.2f}%</td></tr>
    </table>
</body>
</html>"""
        with open(report_path, "w", encoding="utf-8") as f:
            f.write(html_content)

        print("\n" + "=" * 45)
        print(f"  QUANTAEGIS BACKTEST RESULTS: {symbol}")
        print("=" * 45)
        print(f"Total Return:      {metrics['total_return_pct']:+.2f}%")
        print(f"Sharpe Ratio:      {metrics['sharpe_ratio']:.2f}")
        print(f"Calmar Ratio:      {metrics['calmar_ratio']:.2f}")
        print(f"Max Drawdown:      {metrics['max_drawdown_pct']:.2f}%")
        print(f"Win Rate:          {metrics['win_rate']:.2f}%")
        print(f"Profit Factor:     {metrics['profit_factor']:.2f}")
        print(f"Total Trades:      {metrics['total_trades']}")
        print(f"Best Trade:        {metrics['best_trade_pct']:+.2f}%")
        print(f"Worst Trade:       {metrics['worst_trade_pct']:+.2f}%")
        print(f"Report Generated:  {report_path}")
        print("=" * 45 + "\n")

        return report_path

    def run_all(
        self,
        symbols: list[str],
        data_dir: str = "./data",
        initial_cash: float = 10000.0,
    ) -> None:
        aggregate_metrics = []
        for symbol in symbols:
            htf_path = os.path.join(data_dir, f"{symbol}_HTF.csv")
            ltf_path = os.path.join(data_dir, f"{symbol}_LTF.csv")

            if not os.path.exists(htf_path) or not os.path.exists(ltf_path):
                self.logger.warning(
                    f"Data files missing for {symbol}: {htf_path} / {ltf_path}"
                )
                continue

            htf_df = self.load_data_from_csv(htf_path, symbol)
            ltf_df = self.load_data_from_csv(ltf_path, symbol)
            metrics, eq_df = self.run_backtest(
                symbol, htf_df, ltf_df, initial_cash=initial_cash
            )
            self.generate_report(metrics, eq_df)
            aggregate_metrics.append(metrics)

        if aggregate_metrics:
            agg_df = pd.DataFrame(aggregate_metrics)
            print("\n" + "=" * 80)
            print("  AGGREGATE PERFORMANCE COMPARISON")
            print("=" * 80)
            print(
                agg_df[
                    [
                        "symbol",
                        "total_return_pct",
                        "sharpe_ratio",
                        "max_drawdown_pct",
                        "win_rate",
                        "profit_factor",
                    ]
                ].to_string(index=False)
            )
            print("=" * 80 + "\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="QuantAegis Backtester")
    parser.add_argument(
        "--symbols", nargs="+", help="List of symbols to backtest", required=True
    )
    parser.add_argument(
        "--data-dir",
        type=str,
        default="./data",
        help="Directory containing CSV data files",
    )
    parser.add_argument(
        "--initial-cash", type=float, default=10000.0, help="Initial portfolio cash"
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default="./reports",
        help="Directory to save HTML reports",
    )

    args = parser.parse_args()
    runner = BacktestRunner()
    runner.run_all(
        symbols=args.symbols, data_dir=args.data_dir, initial_cash=args.initial_cash
    )
