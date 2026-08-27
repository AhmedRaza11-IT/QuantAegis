"""
cli.py — QuantAegis Standalone Terminal Dashboard & Control Center.

Provides an interactive CLI menu to run:
1. Interactive Web Dashboard & TradingView Charts (http://localhost:8000)
2. Live Trading / Paper Trading Bot (main.py)
3. Backtesting Analysis Engine (XAUUSD, USOIL, BTCUSDT)
4. Automated Test Suite (26 Unit Tests)
5. Send Test WhatsApp & Telegram Alert
"""
import sys
import subprocess
import asyncio
from datetime import datetime, timezone
import webbrowser
from quantaegis.core.config import get_settings
from quantaegis.core.events import SignalEvent
from quantaegis.notifier import TelegramNotifier, WhatsAppNotifier


def print_banner():
    banner = r"""
  ___                  _    _              _     
 / _ \ _   _  __ _ _ _| |_ / \   ___  __ _(_)___ 
| | | | | | |/ _` | '_ \ __/ _ \ / _ \/ _` | / __|
| |_| | |_| | (_| | | | | / ___ \  __/ (_| | \__ \
 \__\_\\__,_|\__,_|_| |_|_\_/   \_\___|\__, |_|___/
                                       |___/      
     Institutional Quantitative Trading Platform
=====================================================
"""
    print(banner)


def show_config():
    settings = get_settings()
    print("\n--- Current Configuration ---")
    print(f"App Environment:     {settings.environment}")
    print(f"Dry Run (Paper):     {settings.app.dry_run}")
    print(f"Risk Per Trade:      {settings.risk.risk_pct_per_trade * 100:.1f}%")
    print(f"Max Daily Drawdown:  {settings.risk.max_daily_drawdown_pct * 100:.1f}%")
    print(f"Max Spread Filter:   {settings.risk.max_spread_pips} pips")
    print(f"MT5 Market Enabled:  {settings.trading.markets.mt5.enabled}")
    print(f"Crypto Enabled:      {settings.trading.markets.crypto.enabled} ({settings.trading.markets.crypto.exchange})")
    print(f"Telegram Alerts:     {'Configured' if settings.telegram_bot_token and not settings.telegram_bot_token.startswith('your_') else 'Disabled'}")
    print(f"WhatsApp Alerts:     {'Enabled (' + settings.whatsapp_provider + ')' if settings.whatsapp_enabled else 'Disabled'}")
    print("-----------------------------\n")


def run_dashboard():
    print("\n[>>] Starting QuantAegis Web Dashboard at http://localhost:8000...\n")
    try:
        webbrowser.open("http://localhost:8000")
    except Exception:
        pass
    import uvicorn
    uvicorn.run("quantaegis.dashboard.app:app", host="127.0.0.1", port=8000, reload=False)


def run_bot():
    print("\n[>>] Launching QuantAegis Trading Orchestrator...\n")
    try:
        from main import main
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n[!] Bot stopped by user.")


def run_backtest():
    print("\n[>>] Running Multi-Asset Backtest Simulation (XAUUSD & BTCUSDT)...\n")
    cmd = [
        sys.executable,
        "-m",
        "quantaegis.backtesting.backtest_runner",
        "--symbols",
        "XAUUSD",
        "BTCUSDT",
        "--data-dir",
        "./data",
        "--initial-cash",
        "10000",
    ]
    subprocess.run(cmd)


def run_tests():
    print("\n[>>] Running Pytest Test Suite...\n")
    cmd = [sys.executable, "-m", "pytest", "tests/", "-v"]
    subprocess.run(cmd)


async def send_test_alerts():
    settings = get_settings()
    print("\n[>>] Sending test signal alert to configured channels...")
    
    tg = TelegramNotifier(
        token=settings.telegram_bot_token or "",
        chat_id=settings.telegram_chat_id or "",
    )
    wa = WhatsAppNotifier(
        enabled=settings.whatsapp_enabled,
        provider=settings.whatsapp_provider,
        phone_number=settings.whatsapp_phone_number,
        api_key=settings.whatsapp_api_key,
        twilio_account_sid=settings.twilio_account_sid,
        twilio_auth_token=settings.twilio_auth_token,
        twilio_from=settings.twilio_whatsapp_from,
    )

    test_signal = SignalEvent(
        symbol="XAUUSD",
        direction="BUY",
        entry_price=2050.50,
        sl=2042.00,
        tp=2067.50,
        timeframe="M15",
        strategy_name="MultiTimeframeTrend",
        timestamp=datetime.now(timezone.utc),
        atr=5.25,
    )

    await tg.on_signal(test_signal)
    await wa.on_signal(test_signal)
    print("Test alert dispatched! Check your Telegram and WhatsApp.\n")


def main_menu():
    while True:
        print_banner()
        show_config()
        print("Select an option:")
        print("  [1] 🌐 Launch Interactive Web Dashboard & Charts (http://localhost:8000)")
        print("  [2] 🤖 Start Live / Paper Trading Bot (Background Streaming)")
        print("  [3] 📊 Run Backtesting Engine on Gold & Crypto")
        print("  [4] 🧪 Run Full Automated Test Suite (26 Unit Tests)")
        print("  [5] 📱 Send Test Alert to Telegram & WhatsApp")
        print("  [6] ❌ Exit")
        print()

        choice = input("Enter choice (1-6): ").strip()

        if choice == "1":
            run_dashboard()
            break
        elif choice == "2":
            run_bot()
            break
        elif choice == "3":
            run_backtest()
            input("\nPress Enter to return to menu...")
        elif choice == "4":
            run_tests()
            input("\nPress Enter to return to menu...")
        elif choice == "5":
            asyncio.run(send_test_alerts())
            input("\nPress Enter to return to menu...")
        elif choice == "6":
            print("\nGoodbye!")
            break
        else:
            print("\nInvalid choice. Please enter 1, 2, 3, 4, 5, or 6.")


if __name__ == "__main__":
    main_menu()
