"""
PolyInsider Bot API v1.0
=========================
API REST pour contrôler le bot, consulter positions/PnL, configurer risk.
WebSocket pour updates temps réel.

Endpoints:
- GET  /api/health       — Bot status
- GET  /api/positions    — Positions ouvertes
- GET  /api/portfolio    — Capital, PnL, stats
- GET  /api/trades       — Historique trades
- GET  /api/wallets      — Wallets trackés
- POST /api/wallets      — Ajouter wallet whitelist
- GET  /api/settings     — Config risk actuelle
- PATCH /api/settings    — Update config
- POST /api/bot/start    — Démarrer bot
- POST /api/bot/stop     — Arrêter bot
- GET  /api/backtest     — Lancer backtest
- WS   /ws/trades        — Feed temps réel
"""
