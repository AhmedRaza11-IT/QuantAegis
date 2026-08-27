import asyncio
from datetime import datetime, timezone
import telegram
from telegram.error import TelegramError, RetryAfter

from quantaegis.core.events import SignalEvent, OrderEvent, FillEvent, ErrorEvent
from quantaegis.core.config import get_settings
from quantaegis.core.logger import get_logger

settings = get_settings()
logger = get_logger("telegram_notifier")

class TelegramNotifier:
    def __init__(self, token: str, chat_id: str):
        self._token = token
        self._chat_id = chat_id
        self._daily_trades: list = []
        self._daily_pnl: float = 0.0
        
        is_valid_token = bool(token and not token.startswith("your_") and token != "dummy")
        self._bot = telegram.Bot(token=token) if is_valid_token else None

    async def send_message(self, text: str, parse_mode: str = 'HTML') -> None:
        if not self._bot or not self._chat_id or self._chat_id.startswith("your_"):
            logger.debug(f"[Telegram Alert (Disabled/No Token)]: {text[:100]}...")
            return
            
        retries = 3
        for attempt in range(retries):
            try:
                await self._bot.send_message(
                    chat_id=self._chat_id,
                    text=text,
                    parse_mode=parse_mode
                )
                break
            except RetryAfter as e:
                logger.warning(f"Telegram rate limit hit. Sleeping for {e.retry_after} seconds.")
                await asyncio.sleep(e.retry_after)
            except TelegramError as e:
                logger.error(f"TelegramError sending message: {e}")
                break
            except Exception as e:
                logger.error(f"Unexpected error sending Telegram message: {e}")
                break

    async def on_signal(self, signal: SignalEvent) -> None:
        if getattr(settings.notifier, 'send_entry_alerts', True):
            emoji = "🟢" if signal.direction.lower() in ("long", "buy") else "🔴"
            message = (
                f"📊 <b>SIGNAL DETECTED</b>\n"
                f"━━━━━━━━━━━━━━━━━━\n"
                f"🏷️ Symbol: {signal.symbol}\n"
                f"📈 Direction: {emoji} {signal.direction}\n"
                f"💰 Entry: {signal.entry_price:.5f}\n"
                f"🛑 Stop Loss: {signal.sl:.5f}\n"
                f"🎯 Take Profit: {signal.tp:.5f}\n"
                f"📐 ATR: {signal.atr:.5f}\n"
                f"⏰ TF: {signal.timeframe}\n"
                f"🕐 Time: {signal.timestamp} UTC"
            )
            await self.send_message(message)

    async def on_order_filled(self, order: OrderEvent, lots: float, risk_usd: float) -> None:
        if getattr(settings.notifier, 'send_entry_alerts', True):
            # Calculate pips approx (assuming standard lot size multiplier logic if needed, simplify here)
            sl_pips = abs(order.entry_price - order.sl) * 10000 if 'JPY' not in order.symbol else abs(order.entry_price - order.sl) * 100
            tp_pips = abs(order.tp - order.entry_price) * 10000 if 'JPY' not in order.symbol else abs(order.tp - order.entry_price) * 100
            
            message = (
                f"✅ <b>ORDER FILLED</b>\n"
                f"━━━━━━━━━━━━━━━━━━\n"
                f"🏷️ Symbol: {order.symbol}\n"
                f"📈 Direction: {order.direction}\n"
                f"📊 Lots: {lots}\n"
                f"💰 Entry Price: {order.entry_price:.5f}\n"
                f"🛑 SL: {order.sl:.5f} ({sl_pips:.1f} pips)\n"
                f"🎯 TP: {order.tp:.5f} ({tp_pips:.1f} pips)\n"
                f"💵 Risk: ${risk_usd:.2f}\n"
                f"🔖 Order ID: {order.order_id}"
            )
            await self.send_message(message)

    async def on_trade_closed(self, fill: FillEvent) -> None:
        pnl = fill.pnl
        self._daily_trades.append(fill)
        self._daily_pnl += pnl
        
        if getattr(settings.notifier, 'send_exit_alerts', True):
            emoji = '🟢' if pnl > 0 else '🔴'
            outcome = '💵 Profit' if pnl > 0 else '💸 Loss'
            message = (
                f"{emoji} <b>TRADE CLOSED</b>\n"
                f"━━━━━━━━━━━━━━━━━━\n"
                f"🏷️ Symbol: {fill.symbol}\n"
                f"💰 Close Price: {fill.fill_price:.5f}\n"
                f"{outcome}: ${pnl:+.2f}\n"
                f"📊 Daily PnL: ${self._daily_pnl:+.2f}\n"
                f"🔖 Order ID: {fill.order_id}"
            )
            await self.send_message(message)

    async def on_kill_switch_triggered(self, drawdown_pct: float, equity: float) -> None:
        message = (
            f"🚨 <b>KILL SWITCH ACTIVATED</b>\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"⚠️ Daily Drawdown Limit Reached!\n"
            f"📉 Drawdown: {drawdown_pct:.2%}\n"
            f"💰 Current Equity: ${equity:.2f}\n"
            f"🛑 Trading HALTED for today"
        )
        await self.send_message(message)

    async def on_error(self, error: ErrorEvent) -> None:
        if getattr(settings.notifier, 'send_error_alerts', True):
            if error.severity in ("ERROR", "CRITICAL"):
                tb_snippet = str(error.traceback_str)[-500:] if error.traceback_str else "No traceback"
                message = (
                    f"🔴 <b>ERROR ALERT</b>\n"
                    f"━━━━━━━━━━━━━━━━━━\n"
                    f"⚙️ Source: {error.source}\n"
                    f"❌ Message: {error.message}\n"
                    f"⏰ Time: {error.timestamp}\n"
                    f"<code>{tb_snippet}</code>"
                )
                await self.send_message(message)

    async def send_daily_summary(self) -> None:
        if getattr(settings.notifier, 'send_daily_summary', True):
            today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
            total = len(self._daily_trades)
            wins = sum(1 for t in self._daily_trades if t.pnl > 0)
            losses = total - wins
            win_rate = (wins / total) if total > 0 else 0.0
            
            gross_profit = sum(t.pnl for t in self._daily_trades if t.pnl > 0)
            gross_loss = abs(sum(t.pnl for t in self._daily_trades if t.pnl < 0))
            profit_factor = (gross_profit / gross_loss) if gross_loss > 0 else (999.0 if gross_profit > 0 else 0.0)
            
            message = (
                f"📊 <b>DAILY TRADING SUMMARY</b>\n"
                f"━━━━━━━━━━━━━━━━━━\n"
                f"📅 Date: {today}\n"
                f"🔢 Total Trades: {total}\n"
                f"✅ Winning Trades: {wins}\n"
                f"❌ Losing Trades: {losses}\n"
                f"📈 Win Rate: {win_rate:.1%}\n"
                f"💰 Daily PnL: ${self._daily_pnl:+.2f}\n"
                f"💵 Profit Factor: {profit_factor:.2f}"
            )
            await self.send_message(message)
            
            # Reset daily counters
            self._daily_trades = []
            self._daily_pnl = 0.0

    async def send_startup_message(self) -> None:
        dry_run_status = "Enabled" if getattr(settings, 'dry_run', False) else "Disabled (LIVE)"
        markets = ", ".join(getattr(settings, 'markets', [])) or "None configured"
        
        message = (
            f"🚀 <b>BOT STARTED</b>\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"⚙️ Dry Run: {dry_run_status}\n"
            f"📈 Markets: {markets}\n"
            f"⏰ Time: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')} UTC"
        )
        await self.send_message(message)

    async def send_shutdown_message(self) -> None:
        message = (
            f"🛑 <b>BOT SHUTDOWN</b>\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"⏰ Time: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')} UTC"
        )
        await self.send_message(message)
