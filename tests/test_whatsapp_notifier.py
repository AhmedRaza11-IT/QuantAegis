import pytest
from unittest.mock import patch, MagicMock, AsyncMock
from datetime import datetime, timezone
from quantaegis.notifier.whatsapp_notifier import WhatsAppNotifier
from quantaegis.core.events import SignalEvent, OrderEvent


@pytest.mark.asyncio
async def test_whatsapp_disabled_by_default():
    notifier = WhatsAppNotifier(enabled=False)
    success = await notifier.send_message("Test message")
    assert not success


@pytest.mark.asyncio
async def test_whatsapp_callmebot_send_success():
    notifier = WhatsAppNotifier(
        enabled=True,
        provider="callmebot",
        phone_number="+1234567890",
        api_key="secret123",
    )

    mock_resp = AsyncMock()
    mock_resp.status = 200

    mock_get_ctx = MagicMock()
    mock_get_ctx.__aenter__ = AsyncMock(return_value=mock_resp)
    mock_get_ctx.__aexit__ = AsyncMock(return_value=None)

    mock_session = MagicMock()
    mock_session.get.return_value = mock_get_ctx

    mock_session_ctx = MagicMock()
    mock_session_ctx.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session_ctx.__aexit__ = AsyncMock(return_value=None)

    with patch("aiohttp.ClientSession", return_value=mock_session_ctx):
        success = await notifier.send_message("Test signal alert")
        assert success


@pytest.mark.asyncio
async def test_whatsapp_twilio_send_success():
    notifier = WhatsAppNotifier(
        enabled=True,
        provider="twilio",
        phone_number="+1234567890",
        twilio_account_sid="AC12345",
        twilio_auth_token="auth123",
        twilio_from="whatsapp:+14155238886",
    )

    mock_resp = AsyncMock()
    mock_resp.status = 201

    mock_post_ctx = MagicMock()
    mock_post_ctx.__aenter__ = AsyncMock(return_value=mock_resp)
    mock_post_ctx.__aexit__ = AsyncMock(return_value=None)

    mock_session = MagicMock()
    mock_session.post.return_value = mock_post_ctx

    mock_session_ctx = MagicMock()
    mock_session_ctx.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session_ctx.__aexit__ = AsyncMock(return_value=None)

    with patch("aiohttp.ClientSession", return_value=mock_session_ctx):
        success = await notifier.send_message("Test order filled alert")
        assert success


@pytest.mark.asyncio
async def test_whatsapp_on_signal():
    notifier = WhatsAppNotifier(
        enabled=True,
        provider="callmebot",
        phone_number="+1234567890",
        api_key="secret123",
    )
    notifier.send_message = AsyncMock(return_value=True)

    signal = SignalEvent(
        symbol="XAUUSD",
        direction="BUY",
        entry_price=2050.0,
        sl=2040.0,
        tp=2070.0,
        timeframe="M15",
        strategy_name="MultiTimeframeTrend",
        timestamp=datetime.now(timezone.utc),
        atr=5.0,
    )
    await notifier.on_signal(signal)
    notifier.send_message.assert_awaited_once()
    sent_text = notifier.send_message.call_args[0][0]
    assert "XAUUSD" in sent_text
    assert "BUY" in sent_text


@pytest.mark.asyncio
async def test_whatsapp_on_order_filled():
    notifier = WhatsAppNotifier(
        enabled=True,
        provider="callmebot",
        phone_number="+1234567890",
        api_key="secret123",
    )
    notifier.send_message = AsyncMock(return_value=True)

    order = OrderEvent(
        order_id="123456",
        symbol="BTCUSDT",
        direction="BUY",
        lots=0.5,
        entry_price=65000.0,
        sl=64000.0,
        tp=67000.0,
        status="FILLED",
        timestamp=datetime.now(timezone.utc),
    )
    await notifier.on_order_filled(order, lots=0.5, risk_usd=500.0)
    notifier.send_message.assert_awaited_once()
    sent_text = notifier.send_message.call_args[0][0]
    assert "BTCUSDT" in sent_text
    assert "65000" in sent_text
