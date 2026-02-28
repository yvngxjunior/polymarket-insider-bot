# PolyInsider Bot - New Features Guide

## 🎯 Overview

Cette mise à jour ajoute 4 fonctionnalités majeures au bot :

1. **Backtest Engine** - Validation historique des stratégies
2. **API REST FastAPI** - Endpoints pour SaaS / Dashboard
3. **Dynamic Wallet Scoring** - Recalcul auto + exclusion underperformers
4. **Rate Limiter** - Protection contre 429 errors Polymarket

---

## 1. Backtest Engine 📊

### Description
Replay trades historiques avec stratégie actuelle (Kelly, TP/SL, filtres) pour valider performance avant live.

### Fichier
`bot/analytics/backtest.py`

### Utilisation

#### Via API
```bash
curl -X POST http://localhost:8001/api/backtest \
  -H "Content-Type: application/json" \
  -d '{
    "start_date": "2026-01-01",
    "end_date": "2026-02-28",
    "initial_capital": 1000.0,
    "wallet_addresses": ["0x123...", "0x456..."]
  }'
```

#### Via Code
```python
from bot.analytics.backtest import BacktestEngine

engine = BacktestEngine(
    start_date="2026-01-01",
    end_date="2026-02-28",
    initial_capital=1000.0,
)

result = await engine.run(wallet_addresses=["0x123..."])
print(result.to_dict())
```

### Métriques retournées
- **Win Rate** : % trades gagnants
- **Sharpe Ratio** : Rendement ajusté au risque (annualisé)
- **Max Drawdown** : Perte maximale depuis pic ($ et %)
- **Total Return** : ROI sur période
- **Profit Factor** : Total gains / Total pertes
- **Trades per Day** : Fréquence moyenne

### Exemple de résultat
```json
{
  "total_trades": 142,
  "win_rate": 68.3,
  "sharpe_ratio": 1.85,
  "max_drawdown": -87.45,
  "max_drawdown_pct": -8.74,
  "total_return_pct": 24.7,
  "profit_factor": 2.3,
  "trades_per_day": 2.4
}
```

---

## 2. API REST FastAPI 🚀

### Description
API complète pour contrôler le bot, consulter positions/PnL, gérer wallets, stream trades live.

### Fichier
`api/main.py`

### Démarrage
```bash
# Standalone
uvicorn api.main:app --host 0.0.0.0 --port 8001 --reload

# Docker
docker-compose up api
```

### Documentation Swagger
http://localhost:8001/docs

### Endpoints disponibles

#### Portfolio & Positions

**GET /api/portfolio**
```json
{
  "total_capital": 1250.45,
  "initial_capital": 1000.0,
  "total_pnl": 250.45,
  "open_positions": 3,
  "return_pct": 25.04
}
```

**GET /api/positions?status=OPEN**
```json
{
  "positions": [
    {
      "token_id": "0x1234...",
      "entry_price": 0.65,
      "amount_usdc": 50.0,
      "side": "BUY",
      "status": "OPEN",
      "pnl_usdc": 12.5,
      "market_question": "Trump wins 2026?"
    }
  ],
  "total": 1
}
```

#### Wallets Management

**GET /api/wallets**
```json
{
  "active_wallets": [
    {
      "address": "0xabc...",
      "score": 0.72,
      "total_trades": 45,
      "win_rate": 0.71,
      "is_whitelisted": true
    }
  ],
  "whitelist_count": 2,
  "blacklist_count": 1,
  "total_active": 12
}
```

**POST /api/wallets/whitelist**
```bash
curl -X POST http://localhost:8001/api/wallets/whitelist \
  -H "Content-Type: application/json" \
  -d '{"address": "0x123...", "score": 0.85}'
```

#### WebSocket - Live Trades

**WS /ws/trades**
```javascript
const ws = new WebSocket('ws://localhost:8001/ws/trades');

ws.onmessage = (event) => {
  const data = JSON.parse(event.data);
  console.log('Trades update:', data.trades);
};
```

Stream toutes les 3s :
```json
{
  "type": "trades_update",
  "trades": [
    {"token_id": "0x123...", "side": "BUY", "pnl": 12.5}
  ],
  "timestamp": "2026-02-28T22:15:00Z"
}
```

---

## 3. Dynamic Wallet Scoring 🎯

### Description
Recalcule automatiquement les win rates de tous les wallets trackés toutes les 24h. Exclut automatiquement ceux < 65%.

### Fichier
`bot/scanner/wallet_scorer.py`

### Configuration
```python
# main.py
from bot.scanner.wallet_scorer import WalletScorer

scorer = WalletScorer(
    notifier=notifier,
    min_trades=10,        # Minimum trades pour score valide
    min_win_rate=0.65,    # Seuil exclusion
    lookback_days=30,     # Fenêtre analyse
)

await scorer.start(interval_hours=24)
```

### Comportement

1. **Toutes les 24h** :
   - Recalcule win rate de chaque wallet (trades des 30 derniers jours)
   - Si WR < 65% → `is_active = False` en DB
   - Notif Telegram d'exclusion
   
2. **Update score si changement > 5%** :
   - Ex: 72% → 68% = update
   - Ex: 71% → 70% = pas d'update (trop proche)

3. **Protection données insuffisantes** :
   - Si < 10 trades sur 30j → garde ancien score

### Telegram notifications
```
⚠️ Wallet Auto-Excluded
Address: 0x1234abcd...
Win Rate: 62.3% (threshold: 65.0%)
```

### Force recalc (API/Telegram)
```python
result = await scorer.force_recalc_wallet("0x123...")
print(result)
# {'address': '0x123...', 'old_score': 0.72, 'new_score': 0.65, 'excluded': False}
```

---

## 4. Rate Limiter 🛡️

### Description
Protection contre rate limits Polymarket API avec token bucket + exponential backoff.

### Fichier
`bot/utils/rate_limiter.py`

### Configuration
```python
from bot.utils.rate_limiter import RateLimiter, get_rate_limiter

# Global limiter (singleton)
limiter = get_rate_limiter()

# Custom limiter
limiter = RateLimiter(
    calls_per_second=10.0,  # Max 10 req/s
    burst_size=20,          # Burst up to 20
    backoff_base=2.0,       # Double backoff each hit
    max_backoff=60.0,       # Cap at 60s
)
```

### Utilisation via décorateur
```python
from bot.utils.rate_limiter import rate_limited

@rate_limited("polymarket_trades")
async def fetch_trades(wallet: str):
    # API call here
    response = await client.get(f"/trades/{wallet}")
    return response.json()
```

### Comportement

1. **Token bucket** :
   - Tokens rechargés à 10/sec
   - Max 20 tokens stockés (burst)
   - 1 token = 1 API call

2. **429 détecté** :
   - Backoff 1s → 2s → 4s → 8s → ... → 60s (max)
   - Utilise `Retry-After` header si dispo

3. **Succès** :
   - Reset backoff à 0s

### Stats
```python
stats = limiter.get_stats()
print(stats)
# {
#   'tokens_available': 18.5,
#   'calls_last_minute': 42,
#   'avg_calls_per_second': 0.7,
#   'endpoints_throttled': 1,
#   'active_backoffs': {'polymarket_trades': 4.0}
# }
```

---

## 🚀 Déploiement Complet

### 1. Pull latest
```bash
git checkout feature/api-backtest-improvements
git pull origin feature/api-backtest-improvements
```

### 2. Install nouvelles dépendances
```bash
pip install -r requirements.txt
```

### 3. Update .env (optionnel)
```env
# Backtest defaults
BACKTEST_START_DATE=2026-01-01
BACKTEST_END_DATE=2026-02-28

# Wallet scoring
WALLET_SCORER_MIN_WR=0.65
WALLET_SCORER_MIN_TRADES=10
WALLET_SCORER_LOOKBACK_DAYS=30

# Rate limiter
RATE_LIMIT_CALLS_PER_SEC=10.0
RATE_LIMIT_BURST=20
```

### 4. Run with API
```bash
# Terminal 1 - Bot
python main.py

# Terminal 2 - API
uvicorn api.main:app --host 0.0.0.0 --port 8001 --reload

# Ou Docker tout-en-un
docker-compose up -d
```

### 5. Test API
```bash
# Health check
curl http://localhost:8001/api/health

# Portfolio
curl http://localhost:8001/api/portfolio

# Backtest
curl -X POST http://localhost:8001/api/backtest \
  -H "Content-Type: application/json" \
  -d '{"start_date": "2026-01-01", "end_date": "2026-02-28", "initial_capital": 1000}'
```

### 6. Swagger UI
Ouvre http://localhost:8001/docs pour tester tous les endpoints interactivement.

---

## 📱 Prochaines étapes

### Tier 1 (haute priorité)
- [ ] Connecter frontend React à l'API
- [ ] Ajouter trailing stop-loss dynamique
- [ ] Implémenter wallet discovery via leaderboard
- [ ] Multi-wallet execution (rotation proxy wallets)

### Tier 2 (nice-to-have)
- [ ] Sentiment analysis Twitter/X
- [ ] Liquidity checker (<$10k volume = skip)
- [ ] Multi-exchange (PredictIt, Metaculus)
- [ ] Telegram inline keyboard (approve/reject trades)

---

## 🐛 Troubleshooting

### API ne démarre pas
```bash
# Check port 8001 libre
lsof -i :8001

# Check logs
docker-compose logs api
```

### Backtest retourne 0 trades
- Vérifier dates (format ISO : 2026-01-01)
- Check DB contient trades sur période
- Run `python migrate.py` si tables manquantes

### Rate limiter trop agressif
```python
# Augmente limits dans bot/utils/rate_limiter.py
limiter = RateLimiter(
    calls_per_second=20.0,  # Double
    burst_size=40,
)
```

### Wallet scorer n'exclut pas
- Check `.env` : `WALLET_SCORER_MIN_WR=0.65`
- Vérifier wallet a ≥ 10 trades sur 30j
- Force recalc manuel : `await scorer.force_recalc_wallet("0x...")`

---

## 📚 Ressources

- [FastAPI Docs](https://fastapi.tiangolo.com/)
- [Sharpe Ratio Explained](https://www.investopedia.com/terms/s/sharperatio.asp)
- [Rate Limiting Best Practices](https://stripe.com/docs/rate-limits)
- [Polymarket API](https://docs.polymarket.com/)

---

**Version**: 1.0.0  
**Date**: 2026-02-28  
**Auteur**: ostrolawzyy-beep
