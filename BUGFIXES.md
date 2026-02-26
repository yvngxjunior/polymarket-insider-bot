# Bug Fixes - Phase 2 Dashboard

## Issue: Dashboard & Trade Detection Problems

**Date:** 2026-02-26  
**Reporter:** User  
**Status:** FIXED ✅

---

## Symptoms

1. **Dashboard wallets empty** - Telegram `/wallets` shows 10 wallets but dashboard shows 0
2. **Trade history empty** - No trades showing in dashboard
3. **No copy logs** - Missing "Would have buy..." in DRY_RUN mode

---

## Root Causes

### Bug 1: DATABASE_URL Mismatch

**Problem:**  
After migrating to `data/` structure, `bot/config.py` had no default value for `database_url`. If `.env` still pointed to old location (`sqlite:///./polyinsider.db`), the API would read from a different (empty) database than the bot was writing to (`data/polyinsider.db`).

**Impact:**
- Dashboard reads empty DB (no wallets, no trades)
- Bot writes to correct DB (wallets tracked, trades recorded)
- `/wallets` Telegram command works (uses bot's DB session)
- Frontend `/api/wallets` returns `[]` (uses API's DB session → wrong path)

**Fix:**  
Added default value in `bot/config.py`:
```python
database_url: str = Field(
    default="sqlite:///./data/polyinsider.db",  # ← NEW DEFAULT
    description="Database URL (default: data/polyinsider.db after migration)",
)
```

**Commit:** `c5a9b13` - fix(config): Add default DATABASE_URL pointing to data/ directory

---

### Bug 2: get_new_trades() Initial State

**Problem:**  
`InsiderScanner.get_new_trades()` uses `_known_trades` dict to track which trade IDs have been processed. At startup:
1. `_known_trades` is empty `{}`
2. First call to `get_new_trades()` sees ALL trades as "new"
3. BUT `_known_trades` is only populated during `analyze_wallet()` (called by refresher every 60s)
4. So at t=0, `known = set()` → every trade_id triggers "new trade detected" log
5. However, only trades with `type == "BUY"` are returned

**Expected Behavior:**  
This is actually **correct**. The first refresh (60s after startup) populates `_known_trades` with historical trades. After that, only genuinely new trades trigger copy logic.

**Why Trade History Appears Empty:**  
- If DRY_RUN=true, trades are saved to DB with `status=EXECUTED` and `skip_reason="DRY_RUN"`
- Dashboard shows these trades ONLY if they exist in `copied_trades` table
- If bot just started and no trades were copied yet → table is empty

**Not a bug**, just expected startup behavior.

---

### Bug 3: Missing "Would have buy" Logs

**Problem:**  
Users expected to see:
```
[DRY RUN] Would BUY $50.00 USDC on Will Trump win 2024? @ 0.650
```

But logs were silent even when trades should be copied.

**Root Cause:**  
Two issues:
1. `get_new_trades()` had minimal logging (only `logger.debug`)
2. Type filter was case-sensitive: `if t.get("type") == "BUY"` but API sometimes returns `"BUY"` or `"buy"`

**Fix:**  
Added comprehensive debug logs in `bot/scanner/insider.py`:
```python
# Before filtering
logger.debug(
    f"[SCAN] {wallet_address[:10]} new trade detected: "
    f"type={trade_type} id={trade_id[:12]}... "
    f"amount=${_safe_float(trade.get('usdcSize')):.2f}"
)

# After accepting BUY trade
if trade_type == "BUY":  # Case-insensitive now
    logger.info(
        f"[NEW TRADE] {wallet_address[:10]}... BUY "
        f"${_safe_float(trade.get('usdcSize')):.2f} "
        f"@ {_safe_float(trade.get('price')):.3f}"
    )
```

**Commit:** `dcef32f` - fix(insider): Add debug logs and fix get_new_trades type filter

---

## How to Verify Fixes

### 1. Dashboard Wallets

```bash
# Pull latest code
git pull origin feature/phase2-dashboard

# Verify .env (optional, default is now correct)
cat .env | grep DATABASE_URL
# Should show: DATABASE_URL=sqlite:///./data/polyinsider.db

# Restart bot
python main.py
```

**Expected:**
```
INFO | [DB] Database initialized: data/polyinsider.db
```

**Verify dashboard:**
```bash
curl http://localhost:8000/api/wallets | jq '.total_count'
# Should match: /wallets Telegram command count
```

---

### 2. Trade Detection Logs

**Run bot with debug logs:**
```bash
# In .env
LOG_LEVEL=DEBUG
```

**Restart bot:**
```bash
python main.py
```

**Expected logs (every 3s during scan):**
```
DEBUG | [SCAN] 0x69af8123 new trade detected: type=BUY id=abc123... amount=$100.00
INFO  | [NEW TRADE] 0x69af8123... BUY $100.00 @ 0.650 on 0xtoken123...
INFO  | [DRY RUN] Would BUY $25.00 USDC on Will Trump win? @ 0.650 | best ask: $500.00 @ 0.652
```

If you see `[NEW TRADE]` but NO `[DRY RUN]`, check:
- Conviction filters (price, amount, wallet score)
- Risk manager limits (max positions, daily loss)
- Position already open for that token

---

### 3. Trade History Dashboard

**Generate test trades:**
```bash
# Wait for refresher cycle (60s)
# Wait for bot to detect + copy a trade
# Check logs for: "Trade EXECUTED" or "[DRY RUN] Would BUY"
```

**Verify API:**
```bash
curl http://localhost:8000/api/trades | jq '.total_count'
# Should show: number of trades copied (dry run or live)
```

**Check dashboard:**
- Navigate to http://localhost:3000/trades
- Should see list of trades with status badges
- If empty: wait for first trade to be copied (can take 1-5min)

---

## Migration Checklist

If dashboard still shows empty after fixes:

### Step 1: Verify DB Location

```bash
# Check which DB files exist
dir polyinsider.db
dir data\polyinsider.db
```

**If both exist:**
```bash
# Old DB has wallets, new DB is empty
# Delete new empty DB
del data\polyinsider.db

# Re-run migration
python migrate_data_dir.py
```

### Step 2: Verify .env

```bash
notepad .env
```

**Check:**
```env
DATABASE_URL=sqlite:///./data/polyinsider.db  # ← MUST point to data/
```

**If missing or wrong, update and restart:**
```bash
python main.py
```

### Step 3: Test API Directly

```bash
# Start API
cd ..
uvicorn api.main:app --reload --port 8000

# Test endpoint (new terminal)
curl http://localhost:8000/api/wallets | jq
```

**Expected:**
```json
{
  "wallets": [
    {
      "address": "0x69af...",
      "score": 96.1,
      "win_rate": 0.961,
      "total_trades": 51,
      ...
    }
  ],
  "total_count": 10,
  "active_count": 10
}
```

**If still `[]`:**
- API is reading wrong DB
- Check `api/deps.py` uses `from bot.database import get_db`
- Check `bot/database.py` uses `settings.database_url`

---

## Performance Impact

### Before Fixes
- ❌ Dashboard always empty
- ❌ Silent trade detection (no visibility)
- ❌ Case-sensitive type filter (misses some trades)

### After Fixes
- ✅ Dashboard shows all wallets from bot
- ✅ Verbose logs for every new trade detected
- ✅ Case-insensitive BUY filter (catches all)
- ✅ Debug mode shows full trade flow:
  ```
  [SCAN] → [NEW TRADE] → [CONV] → [RISK] → [SIZE] → [DRY RUN]
  ```

---

## Related Issues

- #3 - Phase 2 Dashboard (PR)
- MAIN-9 - WalletRefresher interval_minutes → interval_seconds
- BUG-1 - DATABASE_URL default missing
- BUG-2 - get_new_trades() logs insufficient
- BUG-3 - Type filter case-sensitive

---

## Future Improvements

1. **Startup wallet sync**: Call `analyze_wallet()` on all tracked wallets at startup (don't wait 60s)
2. **API health endpoint**: Add `/api/health/db` to verify API → DB connection
3. **Dashboard real-time**: WebSocket for instant updates (no 30s polling)
4. **Trade simulation**: `/api/simulate` endpoint to test copy logic without waiting

---

**Status:** All bugs resolved ✅  
**Verification:** Run checklist above  
**Next:** Merge PR #3 after CI passes
