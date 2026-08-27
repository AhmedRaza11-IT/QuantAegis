from datetime import datetime, timezone
from typing import Tuple

from quantaegis.core.events import SignalEvent, ErrorEvent, event_bus
from quantaegis.core.logger import get_logger

logger = get_logger(__name__)

class RiskManager:
    def __init__(self, settings) -> None:
        self.settings = settings          # full Settings object
        self._risk = settings.risk        # shorthand for risk sub-config
        self._is_halted: bool = False
        self._start_of_day_equity: float = 0.0
        self._open_trades_count: int = 0
        self._daily_pnl: float = 0.0
        self._halt_reason: str = ""

    def initialize_day(self, current_equity: float) -> None:
        self._start_of_day_equity = current_equity
        self._is_halted = False
        self._daily_pnl = 0.0
        logger.info(f"Initialized new trading day. Starting equity: {current_equity:.2f}")

    def calculate_position_size(
        self,
        balance: float,
        entry_price: float,
        sl_price: float,
        pip_value: float,
        lot_step: float,
        min_lot: float,
        max_lot: float,
    ) -> float:
        risk_amount = balance * self._risk.risk_pct_per_trade
        sl_distance = abs(entry_price - sl_price)

        if pip_value == 0 or sl_distance == 0:
            logger.warning("Zero pip_value or sl_distance — cannot calculate position size.")
            return 0.0

        sl_in_pips = sl_distance / pip_value
        pip_value_per_lot = pip_value * 10

        raw_lots = risk_amount / (sl_in_pips * pip_value_per_lot)

        # Round to lot_step precision
        lots = round(raw_lots / lot_step) * lot_step
        # Clamp to [min_lot, max_lot]
        lots = max(min_lot, min(lots, max_lot))

        logger.info(
            f"Position size: risk=${risk_amount:.2f}, SL_pips={sl_in_pips:.2f}, lots={lots}"
        )
        return lots

    async def check_daily_drawdown(self, current_equity: float) -> bool:
        if self._start_of_day_equity <= 0:
            return False

        drawdown_pct = (
            (self._start_of_day_equity - current_equity) / self._start_of_day_equity
        )

        if drawdown_pct >= self._risk.max_daily_drawdown_pct:
            self._is_halted = True
            self._halt_reason = f"Max daily drawdown reached: {drawdown_pct * 100:.2f}%"
            logger.critical(self._halt_reason)

            event_bus.publish(
                ErrorEvent(
                    source="risk_manager.check_daily_drawdown",
                    message=self._halt_reason,
                    traceback_str="",
                    timestamp=datetime.now(timezone.utc),
                    severity="CRITICAL",
                )
            )
            return True
        return False

    async def check_spread_filter(self, symbol: str, current_spread_pips: float) -> bool:
        if current_spread_pips > self._risk.max_spread_pips:
            logger.warning(
                f"Spread filter rejected {symbol}: "
                f"{current_spread_pips:.2f} > {self._risk.max_spread_pips:.2f}"
            )
            return True
        return False

    def check_max_trades(self) -> bool:
        if self._open_trades_count >= self._risk.max_open_trades:
            logger.warning(
                f"Max trades limit reached: "
                f"{self._open_trades_count} >= {self._risk.max_open_trades}"
            )
            return True
        return False

    def on_trade_opened(self) -> None:
        self._open_trades_count += 1
        logger.info(f"Trade opened. Open trades: {self._open_trades_count}")

    def on_trade_closed(self, pnl: float) -> None:
        self._open_trades_count = max(0, self._open_trades_count - 1)
        self._daily_pnl += pnl
        logger.info(f"Trade closed. PNL: {pnl:.2f}. Total open trades: {self._open_trades_count}. Daily PNL: {self._daily_pnl:.2f}")

    async def validate_signal(self, signal: SignalEvent, balance: float, current_equity: float, current_spread_pips: float, pip_value: float, lot_step: float, min_lot: float, max_lot: float) -> Tuple[bool, str, float]:
        if self.is_halted:
            return False, f"Risk manager halted: {self._halt_reason}", 0.0

        is_drawdown = await self.check_daily_drawdown(current_equity)
        if is_drawdown:
            return False, self._halt_reason, 0.0

        is_spread_high = await self.check_spread_filter(signal.symbol, current_spread_pips)
        if is_spread_high:
            return False, "Spread filter rejected (Spread too high)", 0.0

        is_max_trades = self.check_max_trades()
        if is_max_trades:
            return False, "Max open trades reached", 0.0

        lots = self.calculate_position_size(balance, signal.entry_price, signal.sl, pip_value, lot_step, min_lot, max_lot)
        if lots <= 0:
            return False, "Calculated position size is 0", 0.0

        return True, "", lots

    @property
    def is_halted(self) -> bool:
        return self._is_halted

    @property
    def daily_pnl(self) -> float:
        return self._daily_pnl

    @property
    def open_trades_count(self) -> int:
        return self._open_trades_count

    def reset_halt(self) -> None:
        self._is_halted = False
        self._halt_reason = ''
        logger.info("Risk manager halt manually reset.")
