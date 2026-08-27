# 📱 QuantAegis — WhatsApp Alerts & Integration Guide

This guide explains how to connect WhatsApp notifications to **QuantAegis** so you receive real-time trading signals, order execution reports, exit profits/losses, kill-switch alerts, and daily summaries directly on your phone.

---

## 🚀 Quick Setup Methods

QuantAegis supports **5 different WhatsApp delivery backends**. You can configure them either directly in the **Web Dashboard** ([http://localhost:8000](http://localhost:8000)) or by editing your `.env` file.

---

### Option 1: Green API (Recommended — 30-Second QR Code Pairing)

**Green API** is the most reliable, zero-queue solution. It links directly to your WhatsApp account just like WhatsApp Web.

1. **Sign Up:** Go to **[https://console.green-api.com](https://console.green-api.com)** and create a free account.
2. **Create Instance:** In the Green API cabinet, click **Create Instance** and select the **Developer / Free** tariff.
3. **Scan QR Code:** 
   - Click **QR code** in your Green API instance settings.
   - Open WhatsApp on your phone (`03222289855`) ➔ go to **Settings** ➔ **Linked Devices** ➔ **Link a Device** ➔ Scan the QR code on your screen.
4. **Copy Credentials:**
   - **`idInstance`** (e.g. `7103859201`)
   - **`apiTokenInstance`** (e.g. `d2f8c5b6e7a140...`)
5. **Activate in QuantAegis:**
   - Open the Dashboard at `http://localhost:8000` ➔ Click **WhatsApp Setup**.
   - Select **Green API**, enter your phone number (`+923222289855`), **Instance ID**, and **API Token**.
   - Click **Save & Activate** ➔ Click **Test Alert**.

---

### Option 2: UltraMsg API (Instant QR Code Pairing)

1. Sign up at **[https://ultramsg.com](https://ultramsg.com)**.
2. Create an instance and scan the QR code with your WhatsApp.
3. Copy your **Instance ID** (e.g. `instance12345`) and **Token**.
4. In `.env` or Dashboard:
   ```env
   WHATSAPP_ENABLED=true
   WHATSAPP_PROVIDER=ultramsg
   WHATSAPP_PHONE_NUMBER=+923222289855
   WHATSAPP_INSTANCE_ID=instance12345
   WHATSAPP_API_KEY=your_token_here
   ```

---

### Option 3: Custom HTTP Webhook / Local Gateway (WAHA / Baileys)

If you run your own local WhatsApp gateway or automation workflow (e.g. WAHA, Baileys, n8n, Zapier):

1. Set provider to `webhook`.
2. In `.env`:
   ```env
   WHATSAPP_ENABLED=true
   WHATSAPP_PROVIDER=webhook
   WHATSAPP_PHONE_NUMBER=+923222289855
   WHATSAPP_WEBHOOK_URL=https://your-webhook-endpoint.com/api/send
   ```

---

### Option 4: CallMeBot (Direct Message Activation)

1. Open WhatsApp on your phone.
2. Send message: `I allow callmebot to send me messages` to **`+34 644 44 49 64`** (or backup numbers: `+34 644 94 32 39` / `+34 644 73 80 50`).
3. CallMeBot will reply with your personal **API Key**.
4. In `.env`:
   ```env
   WHATSAPP_ENABLED=true
   WHATSAPP_PROVIDER=callmebot
   WHATSAPP_PHONE_NUMBER=+923222289855
   WHATSAPP_API_KEY=your_received_key
   ```

---

### Option 5: Twilio WhatsApp API (Enterprise)

1. Create an account at **[https://www.twilio.com](https://www.twilio.com)**.
2. In `.env`:
   ```env
   WHATSAPP_ENABLED=true
   WHATSAPP_PROVIDER=twilio
   WHATSAPP_PHONE_NUMBER=+923222289855
   TWILIO_ACCOUNT_SID=your_account_sid
   TWILIO_AUTH_TOKEN=your_auth_token
   TWILIO_WHATSAPP_FROM=whatsapp:+14155238886
   ```

---

## 📋 Full `.env` Reference for WhatsApp

```env
# =====================================================
# QuantAegis WhatsApp Alert Settings
# =====================================================
WHATSAPP_ENABLED=true
WHATSAPP_PROVIDER=greenapi          # Options: greenapi | ultramsg | webhook | callmebot | twilio
WHATSAPP_PHONE_NUMBER=+923222289855

# Provider Credentials
WHATSAPP_INSTANCE_ID=7103859201     # Required for Green API / UltraMsg
WHATSAPP_API_KEY=your_token_here    # Required for Green API, UltraMsg, CallMeBot
WHATSAPP_WEBHOOK_URL=               # Required if provider is 'webhook'

# Twilio (Only if provider=twilio)
TWILIO_ACCOUNT_SID=
TWILIO_AUTH_TOKEN=
TWILIO_WHATSAPP_FROM=whatsapp:+14155238886
```

---

## 🔔 Example WhatsApp Alerts You Will Receive

### 1. High-Probability Signal Detected:
```text
📊 *QUANTAEGIS SIGNAL DETECTED*
━━━━━━━━━━━━━━━━━━
🏷️ *Symbol:* BTCUSDT
📈 *Direction:* 🟢 BUY
💰 *Entry:* 65,420.00000
🛑 *Stop Loss:* 64,600.00000
🎯 *Take Profit:* 67,060.00000
📐 *ATR:* 410.00000
⏰ *TF:* M15
🕐 *Time:* 2026-08-27 18:45:00 UTC
```

### 2. Order Execution Confirmation:
```text
✅ *ORDER FILLED*
━━━━━━━━━━━━━━━━━━
🏷️ *Symbol:* BTCUSDT
📈 *Direction:* BUY
📊 *Lots/Size:* 0.25
💰 *Fill Price:* 65,420.00000
🛑 *SL:* 64,600.00000
🎯 *TP:* 67,060.00000
💵 *Risk:* $100.00
🔖 *Order ID:* `ord_9f82b1c4`
```

### 3. Trade Exit & Profit/Loss:
```text
🟢 *TRADE CLOSED*
━━━━━━━━━━━━━━━━━━
🏷️ *Symbol:* BTCUSDT
💰 *Exit Price:* 67,060.00000
💵 *Profit:* +$410.00
📊 *Daily PnL:* +$410.00
🔖 *Order ID:* `ord_9f82b1c4`
```

### 4. Daily Performance Summary:
```text
📊 *DAILY TRADING SUMMARY*
━━━━━━━━━━━━━━━━━━
📅 *Date:* 2026-08-27
🔢 *Total Trades:* 4
✅ *Wins:* 3 | ❌ *Losses:* 1
📈 *Win Rate:* 75.0%
💰 *Daily PnL:* +$525.00
```

---

## 🧪 Testing Your Configuration

You can test your WhatsApp setup at any time:

1. **Via Web Dashboard:** Click the purple **"Test Alert"** button at the top of [http://localhost:8000](http://localhost:8000).
2. **Via CLI:** Run `python cli.py` and select Option `[5] Send Test Alert`.
