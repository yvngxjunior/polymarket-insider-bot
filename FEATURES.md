# 🚀 New Features Guide

## 📊 Trailing Stop-Loss (v1.0)

### Overview
Dynamic stop-loss that follows price movements to protect gains while letting winners run.

### How it works

1. **Initial Phase** (Gain < 15%)
   - Uses fixed SL at -30%
   - No trailing yet

2. **Activation** (Gain >= 15%)
   - Trailing SL activates automatically
   - SL placed 5% below peak price
   - Minimum locked profit: +10%

3. **Trailing Phase**
   - If price goes to +25%, SL moves to +20%
   - If price goes to +35%, SL moves to +30%
   - **SL never moves down** (ratchet effect)

### Configuration

```python
from bot.trading.trailing_stop import TrailingStopConfig

config = TrailingStopConfig(
    activation_gain_pct=0.15,  # Activate after +15%
    trail_distance_pct=0.05,   # Keep SL 5% below peak
    min_locked_profit_pct=0.10,  # Lock at least +10%
    initial_sl_pct=-0.30,      # Fixed SL before activation
)
```

### Benefits

✅ **Protect gains** - Lock in profits automatically  
✅ **Let winners run** - Don't exit too early  
✅ **Reduce losses** - Limit downside on failed trades  
✅ **No manual intervention** - Fully automated  

### Example

```
Entry: $0.40
Price goes to $0.50 (+25%)
  → Trailing SL activates
  → SL placed at $0.47 (+17.5% locked)

Price goes to $0.55 (+37.5%)
  → SL moves to $0.52 (+30% locked)

Price drops to $0.52
  → Exit triggered
  → Profit: +30% (instead of -30% with fixed SL)
```

---

## 🔍 Wallet Discovery (v2.0)

### Overview
Automatically discovers high-performing traders from Polymarket leaderboard and adds them to your tracking list.

### How it works

1. **Scraping**
   - Fetches top 100 traders from Polymarket API
   - Runs every 24 hours (configurable)

2. **Filtering**
   - Win rate >= 70%
   - Volume >= $5,000
   - Trades count >= 20
   - Not already tracked

3. **Scoring**
   - Composite score (0.0 - 1.0)
   - Win rate: 50% weight
   - Volume (log scale): 30% weight
   - Trade count: 20% weight

4. **Auto-add**
   - Qualified wallets added to DB
   - Labeled as "Auto-discovered"
   - Immediate tracking

### Configuration

```python
from bot.scanner.wallet_discovery import WalletDiscoveryConfig

config = WalletDiscoveryConfig(
    min_win_rate=0.70,        # 70% minimum
    min_volume_usd=5000.0,    # $5k minimum
    min_trades=20,            # 20 trades minimum
    fetch_limit=100,          # Top 100 from leaderboard
)
```

### Benefits

✅ **Always up-to-date** - New top traders added automatically  
✅ **Quality filters** - Only high-performers  
✅ **Hands-off** - Runs in background  
✅ **Scalable** - Discover 10-20 new wallets per week  

### Manual Run

```bash
# Test discovery
python -m bot.scanner.wallet_discovery

# Or via API
curl -X POST http://localhost:8001/api/discovery/run
```

---

## 🔧 Integration in main.py

### Quick Setup (3 lines)

```python
from bot.features_integration import get_features_manager

# At bot startup
features = get_features_manager(
    enable_trailing_sl=True,
    enable_wallet_discovery=True,
)
await features.start()

# In trade loop
should_exit, reason, exit_price = features.check_position_exit(
    position_id="pos_123",
    entry_price=0.40,
    current_price=0.52,
    entry_time=entry_time,
)

if should_exit:
    # Execute exit
    logger.info(f"Exiting position: {reason}")
```

### Full Example

```python
import asyncio
from bot.features_integration import get_features_manager

async def main():
    # Initialize features
    features = get_features_manager(
        enable_trailing_sl=True,
        enable_wallet_discovery=True,
    )
    
    await features.start()
    
    try:
        # Your bot logic here
        while True:
            # 1. Check for new trades
            # 2. Check exits with trailing SL
            should_exit, reason, _ = features.check_position_exit(...)
            
            await asyncio.sleep(10)
            
    finally:
        await features.stop()

if __name__ == "__main__":
    asyncio.run(main())
```

---

## 📈 Performance Impact

### Trailing SL

**Before:**
- Win rate: 65%
- Avg win: +20%
- Avg loss: -30%
- Profit factor: 1.4x

**After (estimated):**
- Win rate: 65% (unchanged)
- Avg win: +25% (+25% improvement)
- Avg loss: -30% (unchanged)
- Profit factor: 1.75x (+25% improvement)

### Wallet Discovery

**Manual tracking:**
- 5-10 wallets
- Manual research: 2-3h/week
- Miss new top performers

**Auto discovery:**
- 20-50 wallets
- Zero manual work
- Always tracking best performers
- +30-50% more trade opportunities

---

## 🐛 Troubleshooting

### Trailing SL not activating

```python
# Check if position registered
from bot.trading.trailing_stop import get_trailing_stop_manager

manager = get_trailing_stop_manager()
stats = manager.get_position_stats("your_position_id")
print(stats)
```

### Discovery not finding wallets

```bash
# Check API connectivity
curl https://gamma-api.polymarket.com/leaderboard?limit=10

# Check filters (might be too strict)
config.min_win_rate = 0.65  # Lower to 65%
config.min_volume_usd = 2000  # Lower to $2k
```

### Rate limiting

```python
# Increase delay between requests
config.rate_limit_delay = 2.0  # 2 seconds instead of 1
```

---

## 🎯 Next Steps

1. **Test in dry-run mode** for 24-48h
2. **Monitor logs** for trailing SL activations
3. **Check discovery stats** daily
4. **Adjust thresholds** based on performance
5. **Enable live trading** once validated

---

## 📊 Monitoring

### Via API

```bash
# Get trailing SL stats
curl http://localhost:8001/api/features/trailing-stats

# Get discovery stats
curl http://localhost:8001/api/features/discovery-stats
```

### Via Logs

```bash
# Filter trailing SL events
grep "TRAILING_SL" logs/bot.log

# Filter discovery events
grep "DISCOVERY" logs/bot.log
```

---

## ❓ FAQ

**Q: Can I disable trailing SL for specific positions?**  
A: Not yet, but coming in v2.0

**Q: Does discovery consume a lot of API calls?**  
A: No, only 1 call per 24h to leaderboard endpoint

**Q: What if a discovered wallet starts losing?**  
A: Dynamic Wallet Scoring will auto-exclude it after 10 trades if WR < 65%

**Q: Can I run discovery manually?**  
A: Yes: `python -m bot.scanner.wallet_discovery`

---

**Made with ❤️ for better insider trading**
