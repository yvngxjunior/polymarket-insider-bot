# 🤖 Polymarket Insider Bot

Professional Python bot for tracking smart money and copying insider trades on Polymarket.

## Features

- 🔍 **Insider Scanner** — Detects high win-rate wallets in real-time
- 🐋 **Whale Tracker** — Alerts on large positions (configurable threshold)
- ⚡ **Copy Trading Engine** — Auto-copies trades with risk management
- 🛡️ **Risk Manager** — Position sizing, slippage protection, stop-loss
- 📊 **Performance Tracker** — Full P&L tracking per wallet tracked
- 🔔 **Telegram Alerts** — Real-time notifications with trade details

## Project Structure

```
polymarket-insider-bot/
├── bot/
│   ├── config.py           # Pydantic settings
│   ├── database.py         # SQLAlchemy models + session
│   ├── scanner/
│   │   ├── insider.py      # Insider wallet detection
│   │   └── whale.py        # Whale activity tracker
│   ├── trading/
│   │   ├── engine.py       # Copy trading execution
│   │   ├── risk.py         # Risk management
│   │   └── polymarket.py   # Polymarket API wrapper
│   ├── notifications/
│   │   └── telegram.py     # Telegram alerts
│   └── utils/
│       ├── logger.py       # Loguru setup
│       └── helpers.py      # Utility functions
├── alembic/                # DB migrations
├── tests/
├── .env.example
├── requirements.txt
├── docker-compose.yml
└── main.py                 # Entry point
```

## Quick Start

```bash
# 1. Clone & setup
git clone https://github.com/ostrolawzyy-beep/polymarket-insider-bot
cd polymarket-insider-bot
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt

# 2. Configure
cp .env.example .env
# Edit .env with your keys

# 3. Run (dry-run mode par défaut)
python main.py
```

## ⚠️ Disclaimer
This bot is for educational purposes. Use at your own risk. Never invest more than you can afford to lose.
