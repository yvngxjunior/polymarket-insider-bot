# 🤖 PolyInsider Bot v3.2

**Advanced Copy-Trading Bot for Polymarket** with Trailing Stop-Loss, Auto Wallet Discovery, and Real-time Dashboard.

![Python](https://img.shields.io/badge/python-3.11+-blue.svg)
![License](https://img.shields.io/badge/license-MIT-green.svg)
![Status](https://img.shields.io/badge/status-production-success.svg)

---

## ✨ Features

### 🎯 Core Trading
- **Smart Copy Trading** - Automatically copy trades from top-performing wallets
- **Wallet Scoring System** - Advanced algorithm to identify profitable traders (win rate, ROI, volume)
- **Risk Management** - Position sizing, max trade limits, stop-loss protection
- **Dry Run Mode** - Test strategies without risking capital

### 🔥 NEW in v3.2
- **🎢 Trailing Stop-Loss** - Automatically lock profits when positions reach +15% gain
- **🔍 Auto Wallet Discovery** - Find and track new top traders every 24h
- **📊 Real-time Dashboard** - React dashboard with live stats and WebSocket stream
- **⚡ REST API** - Complete API for bot control and analytics

### 📈 Analytics
- **Portfolio Tracking** - Real-time P&L, win rate, Sharpe ratio
- **Backtest Engine** - Test strategies on historical data
- **Trade History** - Complete audit trail with SQLite database

### 🔔 Notifications
- **Telegram Alerts** - Get notified for every trade, whale move, and signal
- **Convergence Signals** - Alert when multiple insiders bet on the same outcome
- **Whale Tracking** - Monitor large trades (>$10k)

---

## 🚀 Quick Start

### Prerequisites

- Python 3.11+
- Node.js 18+ (for dashboard)
- Polymarket account with API credentials
- Telegram bot token (optional)

### Installation

```bash
# Clone repository
git clone https://github.com/ostrolawzyy-beep/polymarket-insider-bot.git
cd polymarket-insider-bot

# Install Python dependencies
pip install -r requirements.txt

# Install frontend dependencies
cd frontend
npm install
cd ..

# Setup environment
cp .env.example .env
# Edit .env with your credentials
```

### Configuration

Edit `.env` file:

```bash
# Polymarket API (REQUIRED)
POLYMARKET_API_KEY=your_api_key
POLYMARKET_SECRET=your_secret
POLYMARKET_PASSPHRASE=your_passphrase
POLYMARKET_PRIVATE_KEY=0x...

# Trading Config
DRY_RUN=true                    # Set to false for live trading
MAX_TRADE_AMOUNT=100            # Max $ per trade
MIN_WIN_RATE=0.60              # Minimum 60% win rate to copy
MIN_WALLET_SCORE=0.70          # Minimum score 70/100

# Features (NEW v3.2)
TRAILING_SL_ENABLED=true        # Enable trailing stop-loss
TRAILING_SL_ACTIVATION=0.15     # Activate at +15% gain
TRAILING_SL_DISTANCE=0.05       # Trail 5% behind peak
WALLET_DISCOVERY_ENABLED=true   # Auto-discover top wallets

# Telegram (optional)
TELEGRAM_BOT_TOKEN=your_token
TELEGRAM_CHAT_ID=your_chat_id
```

### Run the Bot

```bash
# Start bot
python main.py

# In another terminal, start API
uvicorn api.main:app --host 0.0.0.0 --port 8001 --reload

# In another terminal, start dashboard
cd frontend
npm run dev
```

**Dashboard:** http://localhost:3000  
**API Docs:** http://localhost:8001/docs

---

## 📊 Dashboard

### Features
- **Real-time Stats** - Capital, PnL, win rate, active positions
- **Trailing SL Tracker** - Visual chart showing entry/peak prices
- **Live Trades Stream** - WebSocket-powered real-time trade feed
- **Top Wallets** - List of tracked traders with scores and performance
- **Auto-refresh** - Updates every 5 seconds

### Tech Stack
- React 18 + Vite
- Tailwind CSS
- Recharts (visualizations)
- Axios + WebSocket

---

## 🎯 How Trailing Stop-Loss Works

```
Entry: $0.50
       ↓
+10%:  $0.55  ← Watching...
+15%:  $0.575 ← TRAILING ACTIVATED! 🎢
+18%:  $0.59  ← Peak reached
+13%:  $0.565 ← Still trailing (5% behind peak)
+10%:  $0.55  ← SELL TRIGGERED! 💰 (+10% locked)
```

**Config:**
- **Activation:** +15% gain minimum
- **Trail Distance:** 5% behind peak price
- **Min Locked Profit:** 10% guaranteed

**Result:** Lock profits automatically while letting winners run!

---

## 🔍 Auto Wallet Discovery

Every 24 hours, the bot:

1. **Fetches top traders** from Polymarket leaderboard
2. **Calculates scores** based on:
   - Win rate (30%)
   - Total PnL (25%)
   - Volume (20%)
   - Consistency (15%)
   - Recent activity (10%)
3. **Auto-adds** wallets with score >= 85/100
4. **Sends Telegram alert** for new discoveries

**Current status:** 66 top traders discovered and tracked!

---

## 📡 API Endpoints

### Portfolio
```bash
GET /api/portfolio           # Get portfolio summary
GET /api/positions           # Get all positions
```

### Wallets
```bash
GET /api/wallets             # Get tracked wallets
POST /api/wallets/whitelist  # Add to whitelist
POST /api/wallets/blacklist  # Add to blacklist
```

### Features (NEW)
```bash
GET /api/features/status                    # Overall features status
GET /api/features/trailing-sl/status        # Trailing SL positions
POST /api/features/trailing-sl/config       # Update config
POST /api/features/discovery/run            # Manual discovery
GET /api/features/discovery/stats           # Discovery stats
```

### WebSocket
```bash
WS /ws/trades               # Live trades stream
```

Full API docs: http://localhost:8001/docs

---

## 🚀 Deployment

See [frontend/DEPLOY.md](frontend/DEPLOY.md) for detailed deployment instructions.

### Quick Deploy (Free)

**Frontend (Vercel):**
```bash
cd frontend
npm install -g vercel
vercel --prod
```

**Backend (Railway):**
1. Go to [railway.app](https://railway.app)
2. Deploy from GitHub
3. Add environment variables
4. Done!

**Total cost:** $0/month (free tiers)

---

## 🛠️ Project Structure

```
polymarket-insider-bot/
├── bot/
│   ├── trading/
│   │   ├── engine.py              # Main trading engine
│   │   ├── trailing_stop.py       # NEW: Trailing SL manager
│   │   └── executor.py            # Trade execution
│   ├── scanner/
│   │   ├── wallet_scanner.py      # Wallet scanner
│   │   └── wallet_discovery.py    # NEW: Auto-discovery
│   ├── analytics/
│   │   ├── backtest.py            # Backtesting engine
│   │   └── scorer.py              # Wallet scoring
│   ├── notifications/
│   │   └── telegram.py            # Telegram alerts
│   └── database.py                # SQLite models
├── api/
│   └── main.py                    # FastAPI REST + WebSocket
├── frontend/                      # NEW: React dashboard
│   ├── src/
│   │   ├── components/
│   │   │   ├── Dashboard.jsx
│   │   │   ├── TrailingSLChart.jsx
│   │   │   ├── LiveTradesStream.jsx  # NEW: WebSocket
│   │   │   └── ...
│   │   └── utils/
│   ├── package.json
│   └── DEPLOY.md
├── main.py                        # Bot entry point
├── requirements.txt
└── README.md
```

---

## 🔒 Security

- **Never commit** `.env` or private keys to Git
- **Use dry-run mode** to test before going live
- **Start small** with low `MAX_TRADE_AMOUNT`
- **Monitor closely** during first days
- **Enable 2FA** on Polymarket account

---

## 🐛 Troubleshooting

### Bot won't start
- Check `.env` file exists and has valid credentials
- Verify Python 3.11+ installed: `python --version`
- Install dependencies: `pip install -r requirements.txt`

### No trades being copied
- Verify wallets are being scanned (check logs)
- Lower `MIN_WIN_RATE` or `MIN_WALLET_SCORE` in `.env`
- Check that `DRY_RUN=false` for live trading

### Dashboard not loading data
- Make sure API is running: `http://localhost:8001/api/health`
- Check CORS settings in `api/main.py`
- Verify `VITE_API_URL` in `frontend/.env`

### Telegram not working
- Verify bot token is valid
- Check chat ID is correct
- Test with `/start` command

---

## ⚠️ Disclaimer

This bot is for educational purposes. Trading carries risk. Use at your own risk. Past performance doesn't guarantee future results.

---

**Built with ❤️ for the Polymarket community**

*Last updated: March 2026*
