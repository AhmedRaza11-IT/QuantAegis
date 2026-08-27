# QuantAegis — Institutional Quantitative Trading Platform

QuantAegis is an asynchronous, high-frequency, multi-asset algorithmic trading bot engineered for **Gold (XAUUSD)**, **Crude Oil (USOIL)**, and **USDT Crypto Pairs** (BTCUSDT, ETHUSDT, SOLUSDT).

---

## 🌟 Key Features

- **Multi-Market Engine:** MetaTrader 5 (Forex/Commodities) + CCXT.pro async WebSockets (Binance/Bybit).
- **Multi-Timeframe Trend Confluence Strategy:**
  - HTF (1H/4H): EMA 200/50 trend bias + RSI pullback filter.
  - LTF (5M/15M): MACD crossover trigger + EMA 50 momentum confirmation.
  - Volatility-adaptive ATR Stop-Loss & Take-Profit with dynamic 1:2 R:R bracket orders.
- **Institutional Risk Engine:**
  - Dynamic lot sizing based on account equity & ATR risk distance.
  - Maximum daily drawdown kill-switch (halts trading automatically).
  - Real-time spread & slippage filter.
- **Interactive Web Dashboard & AI Decision Platform (`python dashboard.py`):**
  - High-performance Candlestick, 50 EMA, 200 EMA, RSI, and MACD charts.
  - Quantitative "Invest or Not" Decision Engine with Confluence Scores & Pivot Targets.
  - Multi-asset switcher: Gold (XAUUSD), Crude Oil (USOIL), BTC/USDT, ETH/USDT, SOL/USDT.
- **Multi-Provider WhatsApp Alert Dispatcher:**
  - Full support for **Green API** (QR Code Pairing), **UltraMsg**, **Custom Webhooks**, **CallMeBot**, and **Twilio**.
  - Detailed connection instructions available in [WHATSAPP_SETUP.md](file:///d:/My%20Projects/QuantAegis/WHATSAPP_SETUP.md).

---

## 🚀 Quick Start

### 1. Configure Credentials
Open `.env` and set your credentials:
```env
# Telegram
TELEGRAM_BOT_TOKEN=your_token
TELEGRAM_CHAT_ID=your_chat_id

# WhatsApp Alerts (Free CallMeBot or Twilio)
WHATSAPP_ENABLED=true
WHATSAPP_PROVIDER=callmebot
WHATSAPP_PHONE_NUMBER=+1234567890
WHATSAPP_API_KEY=your_callmebot_api_key

# Safety Mode (Paper Trading)
DRY_RUN=true
```

### 2. Launch Interactive Dashboard
```bash
python cli.py
```

### 3. Run the Bot Directly
```bash
python main.py
```

### 4. Run Backtesting Simulation
```bash
python -m quantaegis.backtesting.backtest_runner --symbols XAUUSD BTCUSDT --data-dir ./data --initial-cash 10000
```

### 5. Run Automated Tests
```bash
pytest tests/ -v
```

---

## 📱 Setting Up WhatsApp Alerts

### Option A: CallMeBot (Free, Instant Setup — Recommended)
1. Add `+34 644 44 49 64` to your WhatsApp contacts (CallMeBot).
2. Send message: `I allow callmebot to send me messages`
3. CallMeBot will reply with your personal **API Key**.
4. Set in `.env`:
   ```env
   WHATSAPP_ENABLED=true
   WHATSAPP_PROVIDER=callmebot
   WHATSAPP_PHONE_NUMBER=+your_country_code_and_number
   WHATSAPP_API_KEY=your_received_api_key
   ```

### Option B: Twilio WhatsApp (Enterprise)
Set in `.env`:
```env
WHATSAPP_ENABLED=true
WHATSAPP_PROVIDER=twilio
WHATSAPP_PHONE_NUMBER=+your_number
TWILIO_ACCOUNT_SID=your_sid
TWILIO_AUTH_TOKEN=your_token
TWILIO_WHATSAPP_FROM=whatsapp:+14155238886
```
