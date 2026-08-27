import asyncio
import signal
import sys
import traceback
from datetime import datetime, timezone
from typing import Dict, Optional

import pandas as pd

from quantaegis.core.config import get_settings
from quantaegis.core.logger import get_logger
from quantaegis.core.events import (
    OHLCVBar, SignalEvent, OrderEvent, FillEvent, ErrorEvent,
    event_bus,
)
from quantaegis.data_feed import MT5DataFeed, CCXTDataFeed
from quantaegis.strategies import MultiTimeframeTrendStrategy
from quantaegis.risk_engine import RiskManager
from quantaegis.execution import MT5Executor, CCXTExecutor
from quantaegis.notifier import TelegramNotifier, WhatsAppNotifier

logger = get_logger(__name__)


class TradingOrchestrator:
    """
    Central async orchestrator that wires data feeds, strategy, risk engine,
    execution layer, and Telegram notifier together via the EventBus.
    """

    def __init__(self) -> None:
        self.settings = get_settings()
        self.logger = logger
        self._running: bool = False
        self._htf_data: Dict[str, pd.DataFrame] = {}
        self._ltf_data: Dict[str, pd.DataFrame] = {}
        self._active_signals: Dict[str, SignalEvent] = {}
        self.MAX_BARS = 500

        self.strategy = MultiTimeframeTrendStrategy(config=self.settings.strategy)
        self.risk_manager = RiskManager(self.settings)

        self.mt5_feed: Optional[MT5DataFeed] = None
        self.ccxt_feed: Optional[CCXTDataFeed] = None
        self.mt5_executor: Optional[MT5Executor] = None
        self.ccxt_executor: Optional[CCXTExecutor] = None

        # ── MT5 connector ────────────────────────────────────────────────────
        mt5_cfg = self.settings.trading.markets.mt5
        if mt5_cfg.enabled:
            mt5_symbols = [s.symbol for s in mt5_cfg.symbols]
            mt5_timeframes = list({mt5_cfg.higher_timeframe, mt5_cfg.lower_timeframe})
            self.mt5_feed = MT5DataFeed(
                login=int(self.settings.mt5_login or 0),
                password=self.settings.mt5_password or "",
                server=self.settings.mt5_server or "",
                path=self.settings.mt5_path or "",
                symbols=mt5_symbols,
                timeframes=mt5_timeframes,
            )
            self.mt5_executor = MT5Executor(settings=self.settings)

        # ── CCXT / Crypto connector ───────────────────────────────────────────
        crypto_cfg = self.settings.trading.markets.crypto
        if crypto_cfg.enabled:
            crypto_timeframes = list({crypto_cfg.higher_timeframe, crypto_cfg.lower_timeframe})
            self.ccxt_feed = CCXTDataFeed(
                exchange_id=crypto_cfg.exchange,
                api_key=self.settings.binance_api_key or "",
                secret=self.settings.binance_secret or "",
                symbols=crypto_cfg.symbols,
                timeframes=crypto_timeframes,
            )
            self.ccxt_executor = CCXTExecutor(
                exchange_id=crypto_cfg.exchange,
                api_key=self.settings.binance_api_key or "",
                secret=self.settings.binance_secret or "",
                dry_run=self.settings.app.dry_run,
            )

        # ── Notifiers (Telegram & WhatsApp) ───────────────────────────────────
        self.notifier = TelegramNotifier(
            token=self.settings.telegram_bot_token or "",
            chat_id=self.settings.telegram_chat_id or "",
        )
        self.whatsapp_notifier = WhatsAppNotifier(
            enabled=self.settings.whatsapp_enabled,
            provider=self.settings.whatsapp_provider,
            phone_number=self.settings.whatsapp_phone_number,
            api_key=self.settings.whatsapp_api_key,
            twilio_account_sid=self.settings.twilio_account_sid,
            twilio_auth_token=self.settings.twilio_auth_token,
            twilio_from=self.settings.twilio_whatsapp_from,
        )

        # Symbol routing helpers
        self._mt5_symbols: set[str] = (
            {s.symbol for s in mt5_cfg.symbols} if mt5_cfg.enabled else set()
        )
        self._crypto_symbols: set[str] = (
            set(crypto_cfg.symbols) if crypto_cfg.enabled else set()
        )
        # Higher-timeframe identifiers (bars on these TFs update HTF store, not LTF)
        self._htf_names: set[str] = {mt5_cfg.higher_timeframe, crypto_cfg.higher_timeframe}

        # Wire up event subscriptions
        event_bus.subscribe(OHLCVBar, self._process_bar)
        event_bus.subscribe(ErrorEvent, self.notifier.on_error)
        event_bus.subscribe(ErrorEvent, self.whatsapp_notifier.on_error)

    # ─────────────────────────────────────────────────────────────────────────
    # Initialisation
    # ─────────────────────────────────────────────────────────────────────────

    def _get_symbol_config(self, symbol: str) -> dict:
        """Return pip/lot config dict for a given symbol."""
        for sym_cfg in self.settings.trading.markets.mt5.symbols:
            if sym_cfg.symbol == symbol:
                return {
                    "pip_value": sym_cfg.pip_value,
                    "lot_step": sym_cfg.lot_step,
                    "min_lot": sym_cfg.min_lot,
                    "max_lot": sym_cfg.max_lot,
                }
        # Crypto defaults — size is in base-currency units
        return {"pip_value": 1.0, "lot_step": 0.001, "min_lot": 0.001, "max_lot": 100.0}

    async def initialize(self) -> None:
        """Connect feeds and executors, snapshot starting equity."""
        self.logger.info("Initializing TradingOrchestrator...")
        initial_equity = 0.0

        if self.mt5_feed and self.mt5_executor:
            try:
                await self.mt5_feed.connect()
                account_info = await self.mt5_executor.get_account_info()
                initial_equity += account_info.get("equity", 0.0)
                self.logger.info("MT5 feed and executor connected successfully.")
            except Exception as e:
                self.logger.warning(
                    f"MT5 terminal could not be connected: {e}. "
                    "Skipping MT5 feed for this session. (Ensure MT5 is installed and running if you wish to trade Gold/Oil)"
                )
                self.mt5_feed = None

        if self.ccxt_feed and self.ccxt_executor:
            try:
                await self.ccxt_feed.connect()
                account_info = await self.ccxt_executor.get_account_info()
                usdt_info = account_info.get("total", {})
                initial_equity += float(usdt_info.get("USDT", 0.0))
                self.logger.info("Crypto CCXT feed connected successfully.")
            except Exception as e:
                self.logger.warning(f"Crypto CCXT feed could not be connected: {e}")
                self.ccxt_feed = None

        if initial_equity <= 0.0:
            initial_equity = 10000.0  # Default paper trading equity

        self.risk_manager.initialize_day(initial_equity)
        await self.notifier.send_startup_message()
        await self.whatsapp_notifier.send_startup_message()

    # ─────────────────────────────────────────────────────────────────────────
    # Main run loop
    # ─────────────────────────────────────────────────────────────────────────

    async def run(self) -> None:
        """Gather all async tasks and run until cancelled."""
        self._running = True
        self.logger.info("Starting orchestrator loops...")

        tasks = [
            asyncio.create_task(event_bus.run(), name="event_bus"),
            asyncio.create_task(self._daily_reset_loop(), name="daily_reset"),
            asyncio.create_task(self._daily_summary_loop(), name="daily_summary"),
        ]

        if self.mt5_feed:
            tasks.append(asyncio.create_task(self._run_mt5_stream(), name="mt5_stream"))
        if self.ccxt_feed:
            tasks.append(asyncio.create_task(self._run_ccxt_stream(), name="ccxt_stream"))

        try:
            await asyncio.gather(*tasks)
        except asyncio.CancelledError:
            self.logger.info("Orchestrator tasks cancelled.")
        except Exception as e:
            self.logger.error(f"Fatal error in main loop: {e}", exc_info=True)
            event_bus.publish(
                ErrorEvent(
                    source="orchestrator.run",
                    message=str(e),
                    traceback_str=traceback.format_exc(),
                    timestamp=datetime.now(timezone.utc),
                    severity="CRITICAL",
                )
            )

    # ─────────────────────────────────────────────────────────────────────────
    # Stream consumers
    # ─────────────────────────────────────────────────────────────────────────

    async def _run_mt5_stream(self) -> None:
        """Drain the MT5 async generator and publish bars."""
        async for bar in self.mt5_feed.stream():
            event_bus.publish(bar)

    async def _run_ccxt_stream(self) -> None:
        """Drain the CCXT async generator and publish bars."""
        async for bar in self.ccxt_feed.stream():
            event_bus.publish(bar)

    # ─────────────────────────────────────────────────────────────────────────
    # Bar processing & signal handling
    # ─────────────────────────────────────────────────────────────────────────

    def _append_bar(self, bar: OHLCVBar, store: Dict[str, pd.DataFrame]) -> None:
        """Append a new OHLCV row to the rolling in-memory store."""
        if bar.symbol not in store:
            store[bar.symbol] = pd.DataFrame(
                columns=["open", "high", "low", "close", "volume"]
            )

        new_row = pd.DataFrame(
            {
                "open": [bar.open],
                "high": [bar.high],
                "low": [bar.low],
                "close": [bar.close],
                "volume": [bar.volume],
            },
            index=[bar.timestamp],
        )

        store[bar.symbol] = pd.concat([store[bar.symbol], new_row])
        if len(store[bar.symbol]) > self.MAX_BARS:
            store[bar.symbol] = store[bar.symbol].iloc[-self.MAX_BARS :]

    async def _process_bar(self, bar: OHLCVBar) -> None:
        """Handle a new OHLCV bar: update stores, evaluate strategy, execute orders."""
        try:
            is_htf = bar.timeframe in self._htf_names
            self._append_bar(bar, self._htf_data if is_htf else self._ltf_data)

            # HTF bars only update the higher-TF store; no entry logic on HTF bars
            if is_htf:
                return

            # Require sufficient history on both timeframes
            if bar.symbol not in self._htf_data or len(self._htf_data[bar.symbol]) < 200:
                return
            if bar.symbol not in self._ltf_data or len(self._ltf_data[bar.symbol]) < 50:
                return

            # One active trade per symbol at a time
            if bar.symbol in self._active_signals:
                return

            signal_event = self.strategy.on_bar(
                bar,
                self._htf_data[bar.symbol],
                self._ltf_data[bar.symbol],
            )
            if not signal_event:
                return

            # Broadcast signal
            event_bus.publish(signal_event)
            await self.notifier.on_signal(signal_event)
            await self.whatsapp_notifier.on_signal(signal_event)

            # Route to the correct executor
            if bar.symbol in self._mt5_symbols:
                executor: Optional[MT5Executor | CCXTExecutor] = self.mt5_executor
            elif bar.symbol in self._crypto_symbols:
                executor = self.ccxt_executor
            else:
                self.logger.warning(f"No executor registered for symbol {bar.symbol}")
                return

            if executor is None:
                self.logger.warning(f"Executor is None for {bar.symbol}")
                return

            account_info = await executor.get_account_info()
            balance = float(account_info.get("balance", 0.0))
            equity = float(account_info.get("equity", balance))
            spread = await executor.get_current_spread(signal_event.symbol)

            sym_cfg = self._get_symbol_config(signal_event.symbol)
            risk_usd = balance * self.settings.risk.risk_pct_per_trade

            valid, rejection_msg, lots = await self.risk_manager.validate_signal(
                signal_event,
                balance,
                equity,
                spread,
                sym_cfg["pip_value"],
                sym_cfg["lot_step"],
                sym_cfg["min_lot"],
                sym_cfg["max_lot"],
            )

            if not valid:
                self.logger.info(
                    f"Signal rejected for {signal_event.symbol}: {rejection_msg}"
                )
                return

            order_event = await executor.place_order(signal_event, lots)
            if order_event and order_event.status == "FILLED":
                event_bus.publish(order_event)
                self.risk_manager.on_trade_opened()
                self._active_signals[signal_event.symbol] = signal_event
                await self.notifier.on_order_filled(order_event, lots, risk_usd)
                await self.whatsapp_notifier.on_order_filled(order_event, lots, risk_usd)

        except Exception as exc:
            self.logger.error(f"Error processing bar for {bar.symbol}: {exc}", exc_info=True)
            event_bus.publish(
                ErrorEvent(
                    source="_process_bar",
                    message=str(exc),
                    traceback_str=traceback.format_exc(),
                    timestamp=datetime.now(timezone.utc),
                )
            )

    # ─────────────────────────────────────────────────────────────────────────
    # Scheduled coroutines
    # ─────────────────────────────────────────────────────────────────────────

    async def _daily_reset_loop(self) -> None:
        """Reset risk manager at each UTC midnight."""
        while self._running:
            now = datetime.now(timezone.utc)
            next_midnight = datetime(
                now.year, now.month, now.day, tzinfo=timezone.utc
            ) + pd.Timedelta(days=1)
            await asyncio.sleep((next_midnight - now).total_seconds())

            initial_equity = 0.0
            if self.mt5_executor:
                info = await self.mt5_executor.get_account_info()
                initial_equity += info.get("equity", 0.0)
            if self.ccxt_executor:
                info = await self.ccxt_executor.get_account_info()
                initial_equity += float(info.get("total", {}).get("USDT", 0.0))

            self.risk_manager.initialize_day(initial_equity)
            self.logger.info("Daily risk manager reset completed.")

    async def _daily_summary_loop(self) -> None:
        """Send Telegram daily summary at 23:55 UTC each day."""
        while self._running:
            now = datetime.now(timezone.utc)
            target = datetime(now.year, now.month, now.day, 23, 55, tzinfo=timezone.utc)
            if now >= target:
                target += pd.Timedelta(days=1)
            await asyncio.sleep((target - now).total_seconds())
            await self.notifier.send_daily_summary()
            await self.whatsapp_notifier.send_daily_summary()

    # ─────────────────────────────────────────────────────────────────────────
    # Shutdown
    # ─────────────────────────────────────────────────────────────────────────

    async def shutdown(self) -> None:
        """Gracefully disconnect feeds and cancel all tasks."""
        self.logger.info("Initiating shutdown sequence...")
        self._running = False

        if self.mt5_feed:
            await self.mt5_feed.disconnect()
        if self.ccxt_feed:
            await self.ccxt_feed.disconnect()

        await self.notifier.send_shutdown_message()
        await self.whatsapp_notifier.send_shutdown_message()

        # Cancel all remaining async tasks
        current = asyncio.current_task()
        pending = [t for t in asyncio.all_tasks() if t is not current]
        for task in pending:
            task.cancel()
        await asyncio.gather(*pending, return_exceptions=True)
        self.logger.info("Shutdown complete.")


# ─────────────────────────────────────────────────────────────────────────────
# Entry point
# ─────────────────────────────────────────────────────────────────────────────

async def main() -> None:
    orchestrator = TradingOrchestrator()
    loop = asyncio.get_running_loop()

    def _request_shutdown() -> None:
        asyncio.create_task(orchestrator.shutdown())

    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, _request_shutdown)
        except (NotImplementedError, OSError):
            # Windows doesn't support all Unix signals via add_signal_handler
            pass

    try:
        await orchestrator.initialize()
        await orchestrator.run()
    except Exception as exc:
        logger.error(f"Orchestrator failed to start: {exc}", exc_info=True)
        sys.exit(1)
    finally:
        await orchestrator.shutdown()


if __name__ == "__main__":
    asyncio.run(main())
