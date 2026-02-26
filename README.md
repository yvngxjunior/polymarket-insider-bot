# CaliforniaCrazy

> **Copy-trade Polymarket insiders** — détecte les wallets smart money, copie leurs positions et gère le risque automatiquement.

[![CI](https://github.com/ostrolawzyy-beep/polymarket-insider-bot/actions/workflows/ci.yml/badge.svg)](https://github.com/ostrolawzyy-beep/polymarket-insider-bot/actions)

---

## Ce que fait le bot

| Module | Description |
|---|---|
| **Copy Trading** | Suit les wallets insiders scorés et copie chaque trade filtré |
| **Whale Tracker** | Alerte sur chaque transaction > `WHALE_THRESHOLD` USDC |
| **Convergence Scanner** | Détecte quand plusieurs insiders betent simultanément sur le même marché |
| **Arbitrage Scanner** | Compare Polymarket ↔ Kalshi — alerte si profit risk-free ≥ 3% |
| **Market Scanner** | Scan async de 5 000+ marchés — détecte arbitrages internes et marchés sous-liquides |
| **LLM Agent** | GPT-4o-mini + RAG sur actualités — identifie les marchés mispriced |
| **Exit Manager** | Ferme automatiquement les positions (TP +20% / SL -30% / résolution / durée max 72h) |
| **Performance Tracker** | Calcul win rate, PnL total, log toutes les 10 boucles |

---

## Architecture

```
main.py v2.1
├── Phase 1 — WhaleTracker
├── Phase 2 — ConvergenceScanner
├── Phase 3 — InsiderScanner + ConvictionFilter + RiskManager + PositionSizer + TradingEngine
├── Phase 4 — ArbitrageScanner          [toutes les 20 boucles ~1 min]
├── Phase 5 — MarketScanner 5k+         [toutes les 100 boucles ~5 min]
├── Phase 6 — LLMAgent GPT-4o-mini      [toutes les 50 boucles ~2.5 min, si activé]
├── Phase 7 — PerformanceTracker        [toutes les 10 boucles ~30s]
└── Background — ExitManager            [toutes les 60s, continu]
```

```
bot/
├── ai/
│   └── llm_agent.py         # GPT-4o-mini + RAG via NewsAPI
├── analytics/
│   └── performance.py       # Win rate, PnL, stats
├── notifications/
│   └── telegram.py          # Toutes les alertes (7 types)
├── scanner/
│   ├── insider.py           # Scan wallets insiders
│   ├── whale.py             # Détection baleines
│   ├── convergence.py       # Multi-insider sur même marché
│   ├── wallet_refresher.py  # Refresh périodique des wallets
│   ├── arbitrage.py         # Cross-platform Poly ↔ Kalshi
│   └── market_scanner.py    # Scan async 5 000+ marchés
├── trading/
│   ├── engine.py            # Exécution trades (DRY RUN / LIVE)
│   ├── risk.py              # Kelly Criterion + limites portefeuille
│   ├── position_manager.py  # Tracking positions ouvertes
│   ├── sizing.py            # Calculateur Kelly standalone
│   ├── filters.py           # ConvictionFilter multi-critères
│   └── exit_manager.py      # TP / SL / durée max auto
└── utils/
    ├── logger.py
    └── helpers.py
```

---

## Installation

```bash
git clone https://github.com/ostrolawzyy-beep/polymarket-insider-bot
cd polymarket-insider-bot
pip install -r requirements.txt
cp .env.example .env
# Remplir .env
python main.py
```

### Via Docker

```bash
cp .env.example .env  # Remplir les variables
docker-compose up -d
docker-compose logs -f
```

---

## Configuration `.env`

```env
# Obligatoire
PRIVATE_KEY=0x...
PROXY_WALLET=0x...
TELEGRAM_BOT_TOKEN=...
TELEGRAM_CHAT_ID=...
DATABASE_URL=sqlite:///./polyinsider.db

# Mode
DRY_RUN=true              # false = trades réels
MAX_TRADE_AMOUNT=50.0     # Max $ par trade copié
MIN_WIN_RATE=0.70         # Win rate minimum du wallet source
MIN_SOURCE_BET_USDC=50.0  # Taille min du bet source

# Optionnel — LLM Agent
LLM_ENABLED=false
OPENAI_API_KEY=sk-...
NEWS_API_KEY=...          # newsapi.org — enrichit le contexte
```

---

## Tests

```bash
pip install pytest pytest-asyncio
pytest tests/ -v
```

---

## Sécurité

- **DRY_RUN=true par défaut** — aucun trade réel tant que tu ne le changes pas
- **Quarter-Kelly** — sizing conservateur, jamais plus de 10% du capital par trade
- **Stop Loss -30%** automatique via ExitManager
- **Daily loss limit -15%** + drawdown limit -25% dans RiskManager

---

## Inspiré de

- [dexorynlabs/polymarket-trading-bot-python](https://github.com/dexorynlabs/polymarket-trading-bot-python) — copy trading
- [CarlosIbCu/polymarket-kalshi-btc-arbitrage-bot](https://github.com/CarlosIbCu/polymarket-kalshi-btc-arbitrage-bot) — arbitrage cross-platform
- [ImMike/polymarket-arbitrage](https://github.com/ImMike/polymarket-arbitrage) — scan haute échelle
- [eiri0k/PolyMarket-AI-agent-trading](https://github.com/eiri0k/PolyMarket-AI-agent-trading) — LLM agent
- [Gabagool2-2/polymarket-trading-bot-python](https://github.com/Gabagool2-2/polymarket-trading-bot-python) — architecture générale
