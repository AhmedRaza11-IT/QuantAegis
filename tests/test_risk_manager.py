import pytest
from datetime import datetime, timezone
from quantaegis.core.events import SignalEvent


@pytest.mark.asyncio
async def test_calculate_position_size_standard(risk_manager):
    # balance: 10000, risk: 1% ($100), entry: 2000, sl: 1990 (sl_dist = 10)
    # pip_value = 0.1 -> sl_in_pips = 100 -> pip_value_per_lot = 1.0 -> lots = 100 / (100 * 1) = 1.0 lot
    lots = risk_manager.calculate_position_size(
        balance=10000.0,
        entry_price=2000.0,
        sl_price=1990.0,
        pip_value=0.1,
        lot_step=0.01,
        min_lot=0.01,
        max_lot=100.0,
    )
    assert lots == 1.0


@pytest.mark.asyncio
async def test_calculate_position_size_clamps_to_min_lot(risk_manager):
    lots = risk_manager.calculate_position_size(
        balance=100.0,
        entry_price=2000.0,
        sl_price=1000.0,
        pip_value=0.1,
        lot_step=0.01,
        min_lot=0.01,
        max_lot=100.0,
    )
    assert lots == 0.01


@pytest.mark.asyncio
async def test_calculate_position_size_clamps_to_max_lot(risk_manager):
    lots = risk_manager.calculate_position_size(
        balance=10000000.0,
        entry_price=2000.0,
        sl_price=1999.9,
        pip_value=0.1,
        lot_step=0.01,
        min_lot=0.01,
        max_lot=50.0,
    )
    assert lots == 50.0


@pytest.mark.asyncio
async def test_daily_drawdown_not_triggered(risk_manager):
    risk_manager.initialize_day(10000.0)
    is_halted = await risk_manager.check_daily_drawdown(current_equity=9900.0)
    assert not is_halted
    assert not risk_manager.is_halted


@pytest.mark.asyncio
async def test_daily_drawdown_triggered(risk_manager):
    risk_manager.initialize_day(10000.0)
    # 6% drawdown on 5% max limit
    is_halted = await risk_manager.check_daily_drawdown(current_equity=9400.0)
    assert is_halted
    assert risk_manager.is_halted


@pytest.mark.asyncio
async def test_spread_filter_rejects_wide_spread(risk_manager):
    is_rejected = await risk_manager.check_spread_filter("XAUUSD", current_spread_pips=10.0)
    assert is_rejected


@pytest.mark.asyncio
async def test_spread_filter_accepts_normal_spread(risk_manager):
    is_rejected = await risk_manager.check_spread_filter("XAUUSD", current_spread_pips=1.5)
    assert not is_rejected


@pytest.mark.asyncio
async def test_max_trades_filter(risk_manager):
    for _ in range(5):
        risk_manager.on_trade_opened()
    assert risk_manager.check_max_trades()


@pytest.mark.asyncio
async def test_validate_signal_full_valid(risk_manager):
    risk_manager.initialize_day(10000.0)
    signal = SignalEvent(
        symbol="XAUUSD",
        direction="BUY",
        entry_price=2000.0,
        sl=1990.0,
        tp=2020.0,
        timeframe="M15",
        strategy_name="MultiTimeframeTrend",
        timestamp=datetime.now(timezone.utc),
    )
    valid, msg, lots = await risk_manager.validate_signal(
        signal=signal,
        balance=10000.0,
        current_equity=10000.0,
        current_spread_pips=1.0,
        pip_value=0.1,
        lot_step=0.01,
        min_lot=0.01,
        max_lot=100.0,
    )
    assert valid
    assert msg == ""
    assert lots > 0


@pytest.mark.asyncio
async def test_validate_signal_halted(risk_manager):
    risk_manager.initialize_day(10000.0)
    await risk_manager.check_daily_drawdown(current_equity=9000.0)
    assert risk_manager.is_halted

    signal = SignalEvent(
        symbol="XAUUSD",
        direction="BUY",
        entry_price=2000.0,
        sl=1990.0,
        tp=2020.0,
        timeframe="M15",
        strategy_name="MultiTimeframeTrend",
        timestamp=datetime.now(timezone.utc),
    )
    valid, msg, lots = await risk_manager.validate_signal(
        signal=signal,
        balance=10000.0,
        current_equity=9000.0,
        current_spread_pips=1.0,
        pip_value=0.1,
        lot_step=0.01,
        min_lot=0.01,
        max_lot=100.0,
    )
    assert not valid
    assert "halted" in msg.lower()
    assert lots == 0.0


@pytest.mark.asyncio
async def test_initialize_day_resets_state(risk_manager):
    risk_manager.initialize_day(10000.0)
    await risk_manager.check_daily_drawdown(current_equity=9000.0)
    assert risk_manager.is_halted

    risk_manager.initialize_day(10000.0)
    assert not risk_manager.is_halted
    assert risk_manager.daily_pnl == 0.0


def test_on_trade_closed_updates_pnl(risk_manager):
    risk_manager.initialize_day(10000.0)
    risk_manager.on_trade_opened()
    risk_manager.on_trade_closed(250.0)
    assert risk_manager.daily_pnl == 250.0
    assert risk_manager.open_trades_count == 0
