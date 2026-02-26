# PolyInsider Bot API

**Version:** 3.1.0  
**Stack:** FastAPI + PostgreSQL  
**Docs:** `/docs` (Swagger UI)

---

## 🚀 Quick Start

### Local Development

```bash
# Install dependencies
pip install -r requirements.txt

# Run API server
uvicorn api.main:app --reload --port 8000

# Open Swagger UI
open http://localhost:8000/docs
```

### Health Check

```bash
curl http://localhost:8000/health
# {"status":"ok","service":"polyinsider-api","version":"3.1.0"}
```

---

## 📚 API Endpoints

### 1. **GET /api/positions**

Get all open positions with TP/SL tracking.

**Response:**
```json
{
  "positions": [
    {
      "trade_id": 42,
      "token_id": "0x1234abcd...",
      "market_question": "Will Trump win 2024?",
      "side": "BUY",
      "entry_price": 0.65,
      "current_price": 0.72,
      "amount_usdc": 25.0,
      "unrealized_pnl": 2.69,
      "tp1_hit": false,
      "tp2_price": 0.85,
      "sl_price": 0.55,
      "opened_at": "2026-02-26T17:30:00Z"
    }
  ],
  "total_count": 1,
  "total_capital_deployed": 25.0
}
```

**cURL:**
```bash
curl http://localhost:8000/api/positions
```

---

### 2. **GET /api/portfolio**

Get current portfolio state (capital, P&L, drawdown).

**Response:**
```json
{
  "total_capital": 523.45,
  "peak_capital": 550.00,
  "daily_pnl": -12.30,
  "drawdown_pct": 0.048,
  "open_positions_count": 3,
  "daily_reset_date": "2026-02-26"
}
```

**cURL:**
```bash
curl http://localhost:8000/api/portfolio
```

---

### 3. **GET /api/trades**

Get paginated trade history (executed/skipped/failed).

**Query Parameters:**
- `page` (int, default=1): Page number
- `per_page` (int, default=50, max=100): Results per page
- `status` (str, optional): Filter by status (`EXECUTED`, `SKIPPED`, `FAILED`)

**Response:**
```json
{
  "trades": [
    {
      "id": 123,
      "source_wallet": "0xabcd1234...",
      "market_question": "Will BTC hit 100k?",
      "token_id": "0x5678efgh...",
      "side": "BUY",
      "amount_usdc": 15.50,
      "price": 0.42,
      "pnl_usdc": 3.20,
      "status": "EXECUTED",
      "skip_reason": null,
      "tx_hash": "0x9abcdef...",
      "created_at": "2026-02-25T14:20:00Z",
      "executed_at": "2026-02-25T14:20:05Z"
    }
  ],
  "total_count": 450,
  "page": 1,
  "per_page": 50
}
```

**cURL:**
```bash
# All trades
curl "http://localhost:8000/api/trades?page=1&per_page=50"

# Only executed trades
curl "http://localhost:8000/api/trades?status=EXECUTED"

# Only skipped trades (page 2)
curl "http://localhost:8000/api/trades?status=SKIPPED&page=2"
```

---

### 4. **GET /api/wallets**

Get list of tracked insider wallets.

**Query Parameters:**
- `active_only` (bool, default=false): Show only active wallets

**Response:**
```json
{
  "wallets": [
    {
      "address": "0x1a2b3c4d5e6f...",
      "label": "Whale #7",
      "score": 87.5,
      "win_rate": 0.73,
      "total_trades": 142,
      "total_profit_usd": 12450.00,
      "is_active": true,
      "is_whale": true,
      "consecutive_losses": 0,
      "entry_timing_score": 0.85,
      "first_seen": "2026-01-15T08:00:00Z",
      "last_activity": "2026-02-26T16:45:00Z"
    }
  ],
  "total_count": 25,
  "active_count": 12
}
```

**cURL:**
```bash
# All wallets
curl http://localhost:8000/api/wallets

# Only active wallets
curl "http://localhost:8000/api/wallets?active_only=true"
```

---

### 5. **GET /health**

Health check endpoint for uptime monitoring.

**Response:**
```json
{
  "status": "ok",
  "service": "polyinsider-api",
  "version": "3.1.0"
}
```

**cURL:**
```bash
curl http://localhost:8000/health
```

---

## 🔐 Authentication

**Current:** None (read-only public endpoints)  
**Phase 2:** JWT tokens for private dashboards

---

## 🌍 CORS

**Current:** `allow_origins=["*"]` (all origins allowed)  
**Production:** Restrict to frontend domain:

```python
# api/main.py
app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://yourdomain.com"],
    ...
)
```

---

## 📊 Swagger UI

**Interactive API documentation:**

- **Swagger UI:** http://localhost:8000/docs
- **ReDoc:** http://localhost:8000/redoc

Try all endpoints directly from the browser!

---

## 🚀 Deployment

See [DEPLOYMENT.md](./DEPLOYMENT.md) for Heroku deployment guide.

**Quick Deploy:**
```bash
heroku create polyinsider-bot
heroku addons:create heroku-postgresql:essential-0
git push heroku feature/phase1-fastapi:main
heroku open /docs
```

---

## 🐛 Error Handling

All endpoints return consistent error format:

```json
{
  "error": "Internal server error",
  "detail": "Database connection failed"
}
```

**HTTP Status Codes:**
- `200` - Success
- `500` - Internal server error

---

## 📈 Next Steps (Phase 2)

- [ ] WebSocket endpoint for real-time updates
- [ ] JWT authentication
- [ ] Rate limiting
- [ ] GraphQL endpoint (optional)
- [ ] Frontend React dashboard

---

## 💬 Support

**Issues:** [GitHub Issues](https://github.com/ostrolawzyy-beep/polymarket-insider-bot/issues)  
**Telegram:** [Bot Notifications]
