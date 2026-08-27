"""
whatsapp_notifier.py — Production Multi-Provider WhatsApp Alert Notifier.

Supported Backends:
1. 'greenapi': Green API (QR-code based, fast & high reliability).
2. 'ultramsg': UltraMsg WhatsApp Gateway (Instant QR-code pairing).
3. 'twilio': Enterprise Twilio WhatsApp Messaging API.
4. 'webhook': Custom HTTP Webhook / WAHA / Local Gateway.
5. 'callmebot': Free CallMeBot Gateway.
"""
import urllib.parse
import aiohttp
from datetime import datetime, timezone
from typing import Optional, Dict, Any

from quantaegis.core.events import SignalEvent, OrderEvent, FillEvent, ErrorEvent
from quantaegis.core.logger import get_logger

logger = get_logger("whatsapp_notifier")


class WhatsAppNotifier:
    """Async WhatsApp notification dispatcher supporting multiple backends."""

    def __init__(
        self,
        enabled: bool = False,
        provider: str = "greenapi",
        phone_number: Optional[str] = None,
        api_key: Optional[str] = None,
        instance_id: Optional[str] = None,
        webhook_url: Optional[str] = None,
        twilio_account_sid: Optional[str] = None,
        twilio_auth_token: Optional[str] = None,
        twilio_from: Optional[str] = None,
    ) -> None:
        self.enabled = enabled
        self.provider = (provider or "greenapi").lower().strip()
        self.phone_number = phone_number or ""
        self.api_key = api_key or ""
        self.instance_id = instance_id or ""
        self.webhook_url = webhook_url or ""
        self.twilio_account_sid = twilio_account_sid or ""
        self.twilio_auth_token = twilio_auth_token or ""
        self.twilio_from = twilio_from or "whatsapp:+14155238886"

        self._daily_trades: list = []
        self._daily_pnl: float = 0.0

        if self.enabled:
            logger.info(f"WhatsApp notifier initialized with provider: {self.provider}")

    async def send_message(self, text: str) -> bool:
        """Send a WhatsApp message via the selected provider."""
        if not self.enabled:
            logger.debug(f"[WhatsApp (Disabled)]: {text[:100]}...")
            return False

        try:
            if self.provider == "greenapi":
                return await self._send_greenapi(text)
            elif self.provider == "ultramsg":
                return await self._send_ultramsg(text)
            elif self.provider == "webhook":
                return await self._send_webhook(text)
            elif self.provider == "twilio":
                return await self._send_twilio(text)
            elif self.provider == "callmebot":
                return await self._send_callmebot(text)
            else:
                logger.error(f"Unsupported WhatsApp provider: {self.provider}")
                return False
        except Exception as e:
            logger.error(f"Error dispatching WhatsApp message ({self.provider}): {e}")
            return False

    async def _send_greenapi(self, text: str) -> bool:
        """Send via Green API (https://green-api.com)."""
        if not self.instance_id or not self.api_key:
            logger.warning("Green API requires instance_id (idInstance) and api_key (apiTokenInstance).")
            return False

        clean_phone = self.phone_number.replace("+", "").replace(" ", "").replace("-", "")
        chat_id = f"{clean_phone}@c.us" if "@" not in clean_phone else clean_phone
        
        # Instance host URL
        host = f"https://api.green-api.com" if not self.instance_id.startswith("http") else self.instance_id
        url = f"{host}/waInstance{self.instance_id}/sendMessage/{self.api_key}"

        payload = {
            "chatId": chat_id,
            "message": text,
        }

        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                if resp.status == 200:
                    logger.info("WhatsApp alert sent via Green API.")
                    return True
                else:
                    body = await resp.text()
                    logger.warning(f"Green API returned status {resp.status}: {body}")
                    return False

    async def _send_ultramsg(self, text: str) -> bool:
        """Send via UltraMsg API (https://ultramsg.com)."""
        if not self.instance_id or not self.api_key:
            logger.warning("UltraMsg requires instance_id and api_key (token).")
            return False

        clean_phone = self.phone_number.replace("+", "").replace(" ", "").replace("-", "")
        url = f"https://api.ultramsg.com/{self.instance_id}/messages/chat"

        data = {
            "token": self.api_key,
            "to": clean_phone,
            "body": text,
        }

        async with aiohttp.ClientSession() as session:
            async with session.post(url, data=data, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                if resp.status == 200:
                    logger.info("WhatsApp alert sent via UltraMsg.")
                    return True
                else:
                    body = await resp.text()
                    logger.warning(f"UltraMsg returned status {resp.status}: {body}")
                    return False

    async def _send_webhook(self, text: str) -> bool:
        """Send via Custom WhatsApp Webhook / Local Gateway."""
        if not self.webhook_url:
            logger.warning("WhatsApp Webhook provider requires webhook_url.")
            return False

        payload = {
            "phone": self.phone_number,
            "message": text,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

        async with aiohttp.ClientSession() as session:
            async with session.post(self.webhook_url, json=payload, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                if resp.status in (200, 201, 204):
                    logger.info("WhatsApp alert sent via Custom Webhook.")
                    return True
                else:
                    body = await resp.text()
                    logger.warning(f"WhatsApp Webhook returned status {resp.status}: {body}")
                    return False

    async def _send_callmebot(self, text: str) -> bool:
        """Send via CallMeBot API."""
        if not self.api_key or self.api_key.startswith("your_"):
            return False

        clean_phone = self.phone_number.replace("+", "").replace(" ", "").replace("-", "")
        encoded_text = urllib.parse.quote(text)
        url = (
            f"https://api.callmebot.com/whatsapp.php?"
            f"phone={clean_phone}&text={encoded_text}&apikey={self.api_key}"
        )

        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                if resp.status == 200:
                    logger.info("WhatsApp alert sent via CallMeBot.")
                    return True
                else:
                    body = await resp.text()
                    logger.warning(f"CallMeBot returned status {resp.status}: {body}")
                    return False

    async def _send_twilio(self, text: str) -> bool:
        """Send via Twilio WhatsApp API."""
        if not self.twilio_account_sid or not self.twilio_auth_token:
            return False

        url = f"https://api.twilio.com/2010-04-01/Accounts/{self.twilio_account_sid}/Messages.json"
        to_number = self.phone_number if self.phone_number.startswith("whatsapp:") else f"whatsapp:{self.phone_number}"

        data = {
            "From": self.twilio_from,
            "To": to_number,
            "Body": text,
        }

        auth = aiohttp.BasicAuth(self.twilio_account_sid, self.twilio_auth_token)
        async with aiohttp.ClientSession(auth=auth) as session:
            async with session.post(url, data=data, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                if resp.status in (200, 201):
                    logger.info("WhatsApp alert sent via Twilio.")
                    return True
                else:
                    body = await resp.text()
                    logger.warning(f"Twilio returned status {resp.status}: {body}")
                    return False

    # ─────────────────────────────────────────────────────────────────────────
    # Event Alert Formatters
    # ─────────────────────────────────────────────────────────────────────────

    async def on_signal(self, signal: SignalEvent) -> None:
        emoji = "🟢" if signal.direction.upper() == "BUY" else "🔴"
        msg = (
            f"📊 *QUANTAEGIS SIGNAL DETECTED*\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"🏷️ *Symbol:* {signal.symbol}\n"
            f"📈 *Direction:* {emoji} {signal.direction}\n"
            f"💰 *Entry:* {signal.entry_price:.5f}\n"
            f"🛑 *Stop Loss:* {signal.sl:.5f}\n"
            f"🎯 *Take Profit:* {signal.tp:.5f}\n"
            f"📐 *ATR:* {signal.atr:.5f}\n"
            f"⏰ *TF:* {signal.timeframe}\n"
            f"🕐 *Time:* {signal.timestamp.strftime('%Y-%m-%d %H:%M:%S')} UTC"
        )
        await self.send_message(msg)

    async def on_order_filled(self, order: OrderEvent, lots: float, risk_usd: float) -> None:
        msg = (
            f"✅ *ORDER FILLED*\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"🏷️ *Symbol:* {order.symbol}\n"
            f"📈 *Direction:* {order.direction}\n"
            f"📊 *Lots/Size:* {lots}\n"
            f"💰 *Fill Price:* {order.entry_price:.5f}\n"
            f"🛑 *SL:* {order.sl:.5f}\n"
            f"🎯 *TP:* {order.tp:.5f}\n"
            f"💵 *Risk:* ${risk_usd:.2f}\n"
            f"🔖 *Order ID:* ```{order.order_id}```"
        )
        await self.send_message(msg)

    async def on_trade_closed(self, fill: FillEvent) -> None:
        pnl = fill.pnl or 0.0
        self._daily_pnl += pnl
        self._daily_trades.append(fill)

        emoji = "🟢" if pnl >= 0 else "🔴"
        pnl_label = "Profit" if pnl >= 0 else "Loss"
        msg = (
            f"{emoji} *TRADE CLOSED*\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"🏷️ *Symbol:* {fill.symbol}\n"
            f"💰 *Exit Price:* {fill.fill_price:.5f}\n"
            f"💵 *{pnl_label}:* ${pnl:+.2f}\n"
            f"📊 *Daily PnL:* ${self._daily_pnl:+.2f}\n"
            f"🔖 *Order ID:* ```{fill.order_id}```"
        )
        await self.send_message(msg)

    async def on_kill_switch_triggered(self, drawdown_pct: float, equity: float) -> None:
        msg = (
            f"🚨 *KILL SWITCH ACTIVATED*\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"⚠️ *Daily Drawdown Limit Reached!*\n"
            f"📉 *Drawdown:* {drawdown_pct:.2%}\n"
            f"💰 *Current Equity:* ${equity:.2f}\n"
            f"🛑 *Trading HALTED for today.*"
        )
        await self.send_message(msg)

    async def on_error(self, error: ErrorEvent) -> None:
        if error.severity in ("ERROR", "CRITICAL"):
            msg = (
                f"🔴 *SYSTEM ERROR ALERT*\n"
                f"━━━━━━━━━━━━━━━━━━\n"
                f"⚙️ *Source:* {error.source}\n"
                f"❌ *Message:* {error.message}\n"
                f"⏰ *Time:* {error.timestamp.strftime('%Y-%m-%d %H:%M:%S')} UTC"
            )
            await self.send_message(msg)

    async def send_daily_summary(self) -> None:
        total = len(self._daily_trades)
        wins = len([t for t in self._daily_trades if (t.pnl or 0.0) > 0])
        losses = len([t for t in self._daily_trades if (t.pnl or 0.0) < 0])
        win_rate = (wins / total) if total > 0 else 0.0

        msg = (
            f"📊 *DAILY TRADING SUMMARY*\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"📅 *Date:* {datetime.now(timezone.utc).strftime('%Y-%m-%d')}\n"
            f"🔢 *Total Trades:* {total}\n"
            f"✅ *Wins:* {wins} | ❌ *Losses:* {losses}\n"
            f"📈 *Win Rate:* {win_rate:.1%}\n"
            f"💰 *Daily PnL:* ${self._daily_pnl:+.2f}"
        )
        await self.send_message(msg)
        self._daily_trades.clear()
        self._daily_pnl = 0.0

    async def send_startup_message(self) -> None:
        msg = (
            f"🚀 *QuantAegis Trading Bot Online*\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"📡 WhatsApp Alert Dispatcher Active ({self.provider})\n"
            f"⏰ {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')} UTC"
        )
        await self.send_message(msg)

    async def send_shutdown_message(self) -> None:
        msg = "🛑 *QuantAegis Trading Bot Shutting Down*"
        await self.send_message(msg)
