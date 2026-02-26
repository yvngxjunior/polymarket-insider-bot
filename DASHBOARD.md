# PolyInsider Bot Dashboard 📊

> **Interface web complète pour configurer et monitorer votre bot de copy trading Polymarket**

Powered by **Claude Sonnet 4.6** 🤖

## 🎯 Fonctionnalités

### Page Settings (Paramètres)

Toutes les fonctionnalités du bot sont configurables via des **toggles, sliders et inputs** :

#### ⚙️ **Core Settings** (Paramètres de base)
- **Dry Run Mode** 🔄 - Activer/désactiver le mode simulation
- **Scan Interval** ⏱️ - Fréquence de scan (1-60 secondes)
- **Initial Capital** 💰 - Capital de départ en USDC

#### 🛡️ **Risk Management** (Gestion du risque)
- **Max Open Positions** 📊 - Nombre max de positions simultanées (1-50)
- **Max Position Size** 📈 - Taille max par position (1-50% du capital)
- **Daily Loss Limit** 🚫 - Perte journalière max avant pause (1-100%)
- **Drawdown Limit** 📉 - Drawdown max depuis le pic (1-100%)
- **Kelly Fraction** 🎲 - Fraction Kelly pour le sizing (1-100%)
- **Convergence Boost** 🚀 - Multiplicateur quand insiders convergent (1-3x)
- **Min/Max Price** 💵 - Limites de prix pour les trades

#### 🎯 **Conviction Filters** (Filtres de qualité)
- **Min Win Rate** ✅ - Win rate minimum du wallet source (0-100%)
- **Min Trades Count** 📊 - Nombre minimum de trades historiques (1-100)
- **Min Source Bet** 💸 - Taille minimum du bet source ($1-$10,000)
- **Min Wallet Score** ⭐ - Score de qualité minimum (0-100%)
- **Max Consecutive Losses** ❌ - Pertes consécutives avant skip (1-20)
- **Whale Threshold** 🐋 - Montant pour alertes whale ($50-$100,000)

#### 🚀 **Advanced Features** (Fonctionnalités avancées)
- **Arbitrage Scanner** 💱
  - Active/désactive le scan d'arbitrage Polymarket vs Kalshi
  - **Min Profit %** - Profit minimum pour signaler une opportunité (1-20%)

- **Market Scanner** 🔍
  - Active/désactive le scan haute échelle (10k+ marchés)
  - **Max Markets** - Nombre max de marchés à scanner (100-20,000)

- **AI Agent (GPT-4o-mini)** 🤖
  - Active/désactive l'analyse IA (nécessite clé OpenAI)
  - **Min Confidence** - Confiance minimum pour agir (50-100%)

#### 🔧 **Advanced Settings** (Paramètres experts)
- **Min Trade Amount** - Montant minimum par trade ($0.5+)
- **Kelly Fraction (Sizer)** - Kelly séparé pour le position sizer
- **Log Level** - Verbosité des logs (DEBUG/INFO/WARNING/ERROR/CRITICAL)

---

## 🚀 Installation

### 1️⃣ **Backend API** (FastAPI)

```bash
cd backend

# Créer environnement virtuel
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# Installer dépendances
pip install fastapi uvicorn pydantic pydantic-settings

# Lancer le serveur
python main.py
```

L'API sera disponible sur **http://localhost:8000**

✅ Test : http://localhost:8000 devrait afficher `{"message": "PolyInsider Bot API v2.0"}`

---

### 2️⃣ **Frontend Dashboard** (Next.js + shadcn/ui)

```bash
cd frontend

# Installer dépendances
npm install
# ou
pnpm install
# ou
yarn install

# Lancer le dev server
npm run dev
```

Le dashboard sera disponible sur **http://localhost:3000**

---

## 📖 Utilisation

### **Configurer le bot**

1. Ouvrir http://localhost:3000/settings
2. Ajuster tous les paramètres via les **toggles et sliders**
3. Cliquer sur **"Save Changes"**
4. ⚠️ **Redémarrer le bot** pour appliquer les modifications

### **Persistance**

Tous les changements sont sauvegardés dans le fichier **`.env`** à la racine du projet.

Les commentaires et l'ordre du fichier sont **préservés**.

---

## 🔑 Variables d'environnement (.env)

Voici **toutes les variables configurables** via le dashboard :

```env
# ── Core ──────────────────────────────────────
DRY_RUN=true                    # Simulation mode
SCAN_INTERVAL=3                 # Scan frequency (seconds)
INITIAL_CAPITAL=500.0          # Starting capital (USDC)

# ── Risk Management ───────────────────────────
MAX_POSITIONS=10                # Max concurrent positions
MAX_POSITION_PCT=0.10          # Max 10% capital per position
MAX_PRICE=0.90                 # Don't buy above 0.90
MIN_PRICE=0.05                 # Don't buy below 0.05
DAILY_LOSS_LIMIT_PCT=0.15      # Pause after 15% daily loss
DRAWDOWN_LIMIT_PCT=0.25        # Pause after 25% drawdown
KELLY_FRACTION=0.25            # Quarter-Kelly sizing
CONVERGENCE_BOOST=1.5          # 1.5x boost on convergence

# ── Conviction Filters ────────────────────────
MIN_WIN_RATE=0.70              # Min 70% win rate
MIN_TRADES_COUNT=15            # Min 15 historical trades
MIN_SOURCE_BET_USDC=50.0       # Min $50 source bet
MIN_WALLET_SCORE=0.65          # Min 65% quality score
MAX_CONSECUTIVE_LOSSES=3       # Skip after 3 losses
WHALE_THRESHOLD=500.0          # Whale alert at $500+

# ── Features ──────────────────────────────────
ARB_ENABLED=true               # Arbitrage scanner ON/OFF
ARB_MIN_PROFIT_PCT=0.03        # Min 3% profit for arb
MARKET_SCAN_ENABLED=true       # Market scanner ON/OFF
MARKET_SCAN_MAX_MARKETS=5000   # Scan up to 5k markets
LLM_ENABLED=false              # AI agent ON/OFF
LLM_MIN_CONFIDENCE=0.75        # Min 75% AI confidence

# ── Advanced ──────────────────────────────────
MIN_TRADE_USDC=2.0             # Min $2 per trade
KELLY_FRACTION_SIZER=0.25      # Sizer Kelly fraction
LOG_LEVEL=INFO                 # DEBUG/INFO/WARNING/ERROR
```

---

## 🎨 UI Components

Le dashboard utilise **shadcn/ui** (Tailwind + Radix UI) :

- **Switch** - Toggles pour boolean (ON/OFF)
- **Slider** - Réglages numériques avec ranges
- **Input** - Saisie libre pour montants
- **Select** - Dropdowns (ex: Log Level)
- **Alert** - Messages de succès/erreur
- **Button** - Actions (Save, Reload)

---

## 📡 API Endpoints

### **GET /api/settings**
Récupère tous les paramètres actuels depuis `.env`

```json
{
  "dry_run": true,
  "scan_interval": 3,
  "initial_capital": 500.0,
  "max_positions": 10,
  ...
}
```

### **PUT /api/settings**
Met à jour le fichier `.env` avec de nouvelles valeurs

```bash
curl -X PUT http://localhost:8000/api/settings \
  -H "Content-Type: application/json" \
  -d '{"dry_run": false, "max_positions": 20}'
```

⚠️ **Note** : Le bot doit être **redémarré** pour appliquer les changements.

---

## 🔧 Architecture

```
polymarket-insider-bot/
├── backend/
│   ├── main.py                 # FastAPI app
│   └── app/
│       └── routers/
│           └── settings.py     # Settings API
├── frontend/
│   └── src/
│       └── app/
│           └── settings/
│               └── page.tsx    # Settings UI
├── bot/
│   └── config.py               # Pydantic settings
├── .env                        # Configuration
└── DASHBOARD.md                # This file
```

---

## 🛠️ Développement

### **Ajouter un nouveau paramètre**

1. **bot/config.py** - Ajouter le champ dans `Settings`
2. **backend/app/routers/settings.py** - Ajouter dans `BotSettings` et `settings_map`
3. **frontend/src/app/settings/page.tsx** - Ajouter l'UI (toggle/slider)

### **Hot Reload**

- Backend : Uvicorn reload automatique sur changement de code
- Frontend : Next.js Fast Refresh automatique

---

## 🐛 Troubleshooting

### **Backend ne démarre pas**
```bash
# Vérifier que Python 3.11+ est installé
python --version

# Vérifier que les dépendances sont installées
pip list | grep fastapi
```

### **Frontend ne compile pas**
```bash
# Supprimer node_modules et réinstaller
rm -rf node_modules package-lock.json
npm install
```

### **API retourne 404 sur /api/settings**
```bash
# Vérifier que le backend tourne sur le bon port
curl http://localhost:8000/health
# Devrait retourner {"status": "healthy"}
```

### **Changes not applied after save**
⚠️ **Redémarrer le bot** ! Les settings sont lues au démarrage depuis `.env`

---

## 📝 TODO (Futures features)

- [ ] **Portfolio Stats** - Visualiser capital, PnL, positions ouvertes
- [ ] **Trade History** - Table des trades avec filtres
- [ ] **Real-time Metrics** - WebSocket pour métriques live
- [ ] **Whale Alerts** - Liste des dernières alertes whale
- [ ] **Insider Leaderboard** - Top wallets suivis
- [ ] **Market Analysis** - Graphiques de marchés actifs
- [ ] **Performance Dashboard** - Win rate, Sharpe, drawdown

---

## 🎉 Crédits

**Développé avec :**
- [Next.js 14](https://nextjs.org) (App Router)
- [FastAPI](https://fastapi.tiangolo.com)
- [shadcn/ui](https://ui.shadcn.com)
- [Tailwind CSS](https://tailwindcss.com)
- **Claude Sonnet 4.6** par Perplexity AI 🚀

---

## 📄 License

Ce dashboard fait partie du projet **PolyInsider Bot**.

Pour toute question : [GitHub Issues](https://github.com/ostrolawzyy-beep/polymarket-insider-bot/issues)
