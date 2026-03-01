# 🤖 Auto-Trading Executor - Complete Guide

> **Automated whale copy-trading with military-grade safety features**  
> Inspired by [dexorynlabs/polymarket-trading-bot-python](https://github.com/dexorynlabs/polymarket-trading-bot-python)

---

## 📊 Current Status

✅ **Phase 1-3 Complete** (Whale Detection + Conviction Scoring)  
🚀 **Phase 4 NEW** : Auto-Trading Executor with DRY-RUN mode

---

## 🎯 What This Does

### **Before Executor (Manual Mode)**
```
1. 🐳 Bot detects whale trade
2. 📊 Bot calculates score
3. 💾 Bot stores in database
4. ❌ YOU must trade manually on Polymarket
```

### **After Executor (Auto Mode)**
```
1. 🐳 Bot detects whale trade
2. 📊 Bot calculates score
3. 🛡️ Bot checks safety limits
4. ✅ Bot EXECUTES trade automatically
5. 💰 You wake up with positions!
```

---

## 🛡️ Safety Features

### **Inspired by dexorynlabs bot** [cite:365][cite:367][cite:368]

| Feature | Description | Default (5€) |
|---------|-------------|---------------|
| **DRY-RUN Mode** | Simulate trades without executing | ✅ ON |
| **Daily Loss Limit** | Stop after losing X USD/day | $3 (60%) |
| **Daily Trade Limit** | Max trades per day | 3 trades |
| **Hourly Trade Limit** | Max trades per hour (anti-spam) | 1 trade |
| **Balance Check** | Verify balance before each order | ✅ Always |
| **Position Sizing** | Cap per position | $2 (40%) |
| **Retry Logic** | Retry failed orders | 3x max |
| **Funding Abort** | Stop on "insufficient balance" | ✅ Immediate |
| **Whale Filters** | Only copy top whales | Score ≥80% |
| **Conviction Filter** | Only high-conviction trades | ≥75% redeem |
| **Minimum Whale Size** | Skip small whale trades | $1000+ |
| **Graceful Shutdown** | Safe CTRL+C handling | ✅ Always |

---

## 💰 Recommended Capital Tiers

### **Tier 1: Micro ($5-10)** ⭐
```bash
TRADE_MULTIPLIER=0.05              # Copy 5%
MAX_POSITION_SIZE_USD=2.0          # Max $2/position
MAX_DAILY_LOSS_USD=3.0             # Stop at -$3
MAX_TRADES_PER_DAY=3               # 3 trades max
EXECUTOR_MIN_WHALE_SCORE=0.80      # Top 20% only
```
**Expected**: 2-3 trades/day, high selectivity

### **Tier 2: Small ($50-100)** 🐥
```bash
TRADE_MULTIPLIER=0.10              # Copy 10%
MAX_POSITION_SIZE_USD=20.0         # Max $20/position
MAX_DAILY_LOSS_USD=30.0            # Stop at -$30
MAX_TRADES_PER_DAY=10              # 10 trades max
EXECUTOR_MIN_WHALE_SCORE=0.70      # Top 30%
```
**Expected**: 5-10 trades/day, more opportunities

### **Tier 3: Medium ($500+)** 🐬
```bash
TRADE_MULTIPLIER=0.20              # Copy 20%
MAX_POSITION_SIZE_USD=100.0        # Max $100/position
MAX_DAILY_LOSS_USD=150.0           # Stop at -$150
MAX_TRADES_PER_DAY=20              # 20 trades max
EXECUTOR_MIN_WHALE_SCORE=0.65      # Top 35%
```
**Expected**: 10-20 trades/day, full automation

---

## 🚀 Quick Start (5€ YOLO Mode)

### **Step 1: Prepare Wallet (10 min)**

```bash
# 1. Create NEW Polygon wallet (MetaMask)
#    ⚠️ IMPORTANT: Use a DEDICATED wallet, NOT your main wallet!

# 2. Get your private key
#    MetaMask → Settings → Security & Privacy → Export Private Key
#    ⚠️ NEVER SHARE THIS KEY!

# 3. Fund the wallet
#    - 5 USDC (for trading)
#    - 0.5 MATIC (~$0.30 for gas)
#    Total: ~$5.30

# How to get USDC on Polygon:
# Option A: Bridge from Ethereum (expensive)
# Option B: Buy on Binance/Coinbase → Withdraw to Polygon
# Option C: Swap MATIC → USDC on Uniswap
```

### **Step 2: Configure .env (5 min)**

```bash
# Copy example file
cp .env.executor.example .env

# Edit .env
nano .env  # or use your favorite editor
```

**Fill these values:**
```bash
# ⚠️ START WITH THESE SETTINGS!
AUTO_TRADING_ENABLED=false  # Keep false for now
EXECUTOR_DRY_RUN=true       # Test mode first!

# Your wallet info
PRIVATE_KEY=abc123...       # WITHOUT 0x prefix
PROXY_WALLET=0xYourAddress...

# Safety limits (recommended for 5€)
TRADE_MULTIPLIER=0.05
MAX_POSITION_SIZE_USD=2.0
MAX_DAILY_LOSS_USD=3.0
MAX_TRADES_PER_DAY=3
MAX_TRADES_PER_HOUR=1

# Whale filters (STRICT)
EXECUTOR_MIN_WHALE_SCORE=0.80
EXECUTOR_MIN_CONVICTION=0.75
EXECUTOR_MIN_WHALE_TRADE_SIZE=1000.0
```

### **Step 3: Test in DRY-RUN (1-2 days)**

```bash
# Start the bot
python main.py

# You should see:
[EXECUTOR] 🎭 DRY-RUN MODE | Trades will be simulated
[EXECUTOR] 🚀 Trade executor started

# When a trade is detected:
[EXECUTOR] 🎭 DRY-RUN | Trade 123 | 
           Whale: 0x2e69bb3d... (score: 0.94) |
           Side: BUY | Whale: $2000.00 | Us: $1.50 (5%)

[EXECUTOR] 🎭 DRY-RUN SUCCESS | Would BUY $1.50 on market...
```

**What to check:**
- ✅ Are whales being filtered correctly? (score ≥80%)
- ✅ Are trade sizes reasonable? ($1-2 per trade)
- ✅ Is the bot respecting limits? (max 1 trade/hour)
- ✅ Do the selected whales have high conviction?

### **Step 4: Enable REAL Trading (when ready)**

⚠️ **ONLY do this after 1-2 days of DRY-RUN testing!**

```bash
# Edit .env
AUTO_TRADING_ENABLED=true   # 🚨 DANGER ZONE!
EXECUTOR_DRY_RUN=false      # Real money now!

# Restart bot
python main.py

# You should see:
[EXECUTOR] 💰 LIVE MODE | Real trades will be executed!
[EXECUTOR] 🚀 Trade executor started |
           Limits: $3/day, 3/day, 1/hour

# When a trade executes:
[EXECUTOR] 💰 EXECUTING | Trade 456 |
           Whale: 0x2537fa33... (score: 0.91)

[EXECUTOR] ✅ TRADE EXECUTED | TX: 0xabc123... |
           BUY $1.50
```

---

## 📊 Expected Results (5€ Capital)

### **Day 1 Scenario**

```
04:00 - Bot starts with $5.00 USDC

05:15 - Whale 0x2e69bb3d (score 0.94) buys $2000
        Bot copies: $2000 × 0.05 = $100... 
        → Capped at $1.50 (balance limit)
        ✅ Trade executed: -$1.50
        Balance: $3.50 USDC + 1 position

06:30 - Whale 0x2537fa33 (score 0.91) buys $1500
        Bot copies: $1.50
        ✅ Trade executed: -$1.50
        Balance: $2.00 USDC + 2 positions

07:00 - Whale 0x99768740 (score 0.05) buys $3000
        ❌ SKIPPED: Low whale score

08:00 - Whale 0xe2483825 (score 0.86) buys $800
        ❌ SKIPPED: Whale trade < $1000

09:00 - Whale 0xdd92232b (score 0.82) buys $2000
        ❌ SKIPPED: Hourly limit reached (1/hour)

End of Day 1:
- Cash: $2.00 USDC
- Positions: 2 × $1.50 = $3.00
- Total: $5.00
- Trades: 2/3 used
```

### **Possible Outcomes**

**🚀 Scenario A: Both markets resolve YES (GOOD)**
```
- Position 1: $1.50 → $2.25 (+50%)
- Position 2: $1.50 → $2.25 (+50%)
- Total: $2.00 + $4.50 = $6.50
- Profit: +$1.50 (30% ROI)
```

**💸 Scenario B: Both markets resolve NO (BAD)**
```
- Position 1: $1.50 → $0.25 (-83%)
- Position 2: $1.50 → $0.25 (-83%)
- Total: $2.00 + $0.50 = $2.50
- Loss: -$2.50 (50% loss)
```

**😐 Scenario C: Mixed (1 WIN, 1 LOSS)**
```
- Position 1: $1.50 → $2.25 (+50%)
- Position 2: $1.50 → $0.25 (-83%)
- Total: $2.00 + $2.50 = $4.50
- Loss: -$0.50 (10% loss)
```

---

## 🚨 What Can Go Wrong

### **Problem 1: Whales Are Wrong**

```
Symptom: Your positions keep losing
Cause: Even top whales can be wrong
Solution: 
  - Check whale conviction scores
  - Increase EXECUTOR_MIN_WHALE_SCORE to 0.85+
  - Reduce MAX_TRADES_PER_DAY
```

### **Problem 2: No Trades Executing**

```
Symptom: Bot runs but never trades
Reasons:
  1. Filters too strict:
     - Lower EXECUTOR_MIN_WHALE_SCORE to 0.70
     - Lower EXECUTOR_MIN_CONVICTION to 0.60
     - Lower EXECUTOR_MIN_WHALE_TRADE_SIZE to 500
  
  2. No qualifying whales:
     - Check [WHALE_EXIT] logs
     - Are there any whales with score >0.80?
  
  3. Limits already hit:
     - Check "Daily trade limit hit" warnings
     - Wait until next day/hour
```

### **Problem 3: "Insufficient Balance" Errors**

```
Symptom: [EXECUTOR] Funding error detected
Cause: Not enough USDC or MATIC for gas
Solution:
  - Add more USDC to wallet
  - Add more MATIC (need ~0.5 for gas)
  - Check allowances on Polymarket
```

### **Problem 4: Daily Loss Limit Hit**

```
Symptom: [SAFETY] DAILY LOSS LIMIT HIT
Cause: Lost $3+ today
Solution:
  - Bot will auto-stop until midnight
  - Review why trades lost
  - Consider increasing EXECUTOR_MIN_WHALE_SCORE
  - Wait for reset at 00:00
```

---

## 🔧 Troubleshooting

### **Check Bot Status**

```bash
# Is executor running?
grep "\[EXECUTOR\]" logs/bot.log

# Recent trades?
grep "DRY-RUN SUCCESS\|TRADE EXECUTED" logs/bot.log | tail -10

# Any errors?
grep "ERROR\|FAILED" logs/bot.log | tail -20
```

### **Check Safety Limits**

```python
# In Python shell
from bot.trading.executor import get_executor

executor = get_executor()
if executor:
    safety = executor.safety
    print(f"Daily loss: ${safety.daily_loss_usd:.2f}")
    print(f"Trades today: {safety.trades_today}")
    print(f"Trades this hour: {safety.trades_this_hour}")
```

### **Check Pending Trades**

```python
# In Python shell
from bot.database import get_db, CopiedTrade, TradeStatus

with get_db() as db:
    pending = db.query(CopiedTrade).filter(
        CopiedTrade.status == TradeStatus.DETECTED
    ).count()
    print(f"Pending trades: {pending}")
    
    executed = db.query(CopiedTrade).filter(
        CopiedTrade.status == TradeStatus.EXECUTED
    ).count()
    print(f"Executed trades: {executed}")
```

---

## ⚙️ Advanced Configuration

### **Adjust for Your Risk Tolerance**

**Conservative (Survive longer)**
```bash
TRADE_MULTIPLIER=0.03              # Copy 3% only
MAX_POSITION_SIZE_USD=1.5          # Smaller positions
MAX_DAILY_LOSS_USD=2.0             # Stop at -$2
EXECUTOR_MIN_WHALE_SCORE=0.85      # Top 15% only
EXECUTOR_MIN_CONVICTION=0.80       # Very high conviction
```

**Aggressive (More action)**
```bash
TRADE_MULTIPLIER=0.10              # Copy 10%
MAX_POSITION_SIZE_USD=2.5          # Bigger positions
MAX_DAILY_LOSS_USD=4.0             # Allow -$4
MAX_TRADES_PER_DAY=5               # More trades
EXECUTOR_MIN_WHALE_SCORE=0.75      # Top 25%
```

### **Fine-tune Whale Selection**

```bash
# Only copy specific whales (whitelist)
WALLET_WHITELIST=0x2e69bb3d...,0x2537fa33...

# Never copy specific whales (blacklist)
WALLET_BLACKLIST=0x99768740...,0x5da48936...
```

---

## 📊 Monitoring & Analytics

### **Key Metrics to Track**

```bash
# Daily P&L
grep "Daily reset" logs/bot.log

# Win rate
# (Count EXECUTED trades with profit vs loss)

# Average hold time
# (Time between EXECUTED and market resolution)

# Whale score distribution
# (Are you copying mostly 0.80+ whales?)
```

### **Performance Review (Weekly)**

```
Questions to ask:
1. Total trades executed?
2. Win rate? (% of profitable trades)
3. Average profit per trade?
4. Best performing whale?
5. Worst performing whale?
6. Any patterns in losses?
7. Are safety limits working?
8. Should I adjust filters?
```

---

## ⚠️ CRITICAL DISCLAIMERS

### **🛑 RISKS**

1. **Capital Loss**: You can lose ALL your capital
2. **Whale Risk**: Top whales can be wrong
3. **Market Risk**: Prediction markets are volatile
4. **Smart Contract Risk**: Polymarket contracts could have bugs
5. **Bot Risk**: This code could have bugs
6. **No Stop-Loss**: Positions don't auto-exit on loss
7. **No Guarantees**: Past performance ≠ future results

### **✅ SAFETY RULES**

1. **Dedicated Wallet**: NEVER use your main wallet
2. **Micro Capital**: Start with $5-10 MAX
3. **Test First**: Run DRY-RUN for 1-2 days minimum
4. **Monitor Actively**: Watch first 24h closely
5. **Manual Exit**: You must sell positions manually if needed
6. **Understand Risk**: Only invest what you can afford to lose

### **📜 LEGAL**

- Use at your own risk
- No warranty or guarantees
- Not financial advice
- Not responsible for losses
- Check local gambling/trading laws

---

## 👍 Support & Community

### **Getting Help**

1. Check logs: `logs/bot.log`
2. Read this README fully
3. Check existing GitHub issues
4. Create new issue with:
   - Log snippet (remove private keys!)
   - .env config (remove private keys!)
   - Expected vs actual behavior

### **Contributing**

Pull requests welcome! Focus areas:
- Better error handling
- More safety features
- Performance optimizations
- Documentation improvements

---

## 🚀 What's Next

### **Planned Features**

- [ ] Auto-exit on whale dump
- [ ] Stop-loss orders
- [ ] Take-profit orders
- [ ] Multi-whale consensus (only trade if 3+ whales agree)
- [ ] Market momentum filters
- [ ] Telegram trade approval (click to confirm)
- [ ] Web dashboard
- [ ] Backtest mode (simulate on historical data)

### **Future Improvements**

- Better balance checking
- Gas price optimization
- Trade aggregation (combine small trades)
- Position exit strategies
- Performance analytics dashboard

---

## 🎉 Conclusion

You now have a **production-ready auto-trading executor** with:

✅ DRY-RUN mode for safe testing  
✅ Military-grade safety limits  
✅ Whale quality filters  
✅ Real-time execution  
✅ Comprehensive logging  

**Next steps:**
1. Configure `.env` with your wallet
2. Test in DRY-RUN for 1-2 days
3. Enable real trading when confident
4. Monitor and adjust filters
5. Scale up capital if profitable

**Good luck and trade responsibly!** 👊

---

*Built with inspiration from [dexorynlabs/polymarket-trading-bot-python](https://github.com/dexorynlabs/polymarket-trading-bot-python)*
