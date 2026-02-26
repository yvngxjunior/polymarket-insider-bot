from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import func, desc
from datetime import datetime, timedelta
from typing import List

from bot.database import get_db
from bot.models import Wallet, Trade, Position

router = APIRouter()

@router.get("/dashboard")
async def get_dashboard(db: Session = Depends(get_db)):
    """Real-time dashboard data from database"""
    
    # === LIVE STATUS ===
    now = datetime.now()
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    
    # Total PnL (sum all closed trades)
    total_pnl = db.query(func.sum(Trade.profit_loss)).filter(
        Trade.exit_price.isnot(None)
    ).scalar() or 0.0
    
    # Daily PnL (trades closed today)
    daily_pnl = db.query(func.sum(Trade.profit_loss)).filter(
        Trade.exit_price.isnot(None),
        Trade.exit_time >= today_start
    ).scalar() or 0.0
    
    # Last trade timestamp
    last_trade = db.query(Trade).order_by(desc(Trade.entry_time)).first()
    last_trade_ts = int(last_trade.entry_time.timestamp()) if last_trade else int(now.timestamp()) - 3600
    
    # Mock RPC/Gas for now (TODO: add real monitoring)
    rpc_latency = 42  # ms
    gas_price = 35    # gwei
    wallet_balance = 5000.0  # USDC (TODO: fetch from wallet)
    
    live_status = {
        "botActive": True,  # TODO: check bot process status
        "totalPnL": round(total_pnl, 2),
        "dailyPnL": round(daily_pnl, 2),
        "rpcLatency": rpc_latency,
        "gasPrice": gas_price,
        "walletBalance": wallet_balance,
        "lastTradeTimestamp": last_trade_ts
    }
    
    # === TARGETS (Tracked Wallets) ===
    wallets = db.query(Wallet).filter(Wallet.is_active == True).all()
    targets = []
    
    for wallet in wallets[:10]:  # Limit to 10 most active
        # Calculate wallet stats
        trades = db.query(Trade).filter(
            Trade.wallet_address == wallet.address,
            Trade.exit_price.isnot(None)
        ).all()
        
        total_trades = len(trades)
        winning_trades = len([t for t in trades if t.profit_loss and t.profit_loss > 0])
        winrate = (winning_trades / total_trades * 100) if total_trades > 0 else 0.0
        
        # ROI 7d
        week_ago = now - timedelta(days=7)
        recent_pnl = sum([t.profit_loss or 0 for t in trades if t.exit_time and t.exit_time >= week_ago])
        roi_7d = (recent_pnl / wallet.total_volume * 100) if wallet.total_volume > 0 else 0.0
        
        # Volume 24h
        day_ago = now - timedelta(days=1)
        volume_24h = sum([t.size or 0 for t in trades if t.entry_time >= day_ago])
        
        # Last trade age
        last_wallet_trade = db.query(Trade).filter(
            Trade.wallet_address == wallet.address
        ).order_by(desc(Trade.entry_time)).first()
        last_trade_age = int((now - last_wallet_trade.entry_time).total_seconds()) if last_wallet_trade else 3600
        
        targets.append({
            "address": wallet.address,
            "name": wallet.label or f"{wallet.address[:6]}...{wallet.address[-4:]}",
            "winrate": round(winrate, 1),
            "roi7d": round(roi_7d, 1),
            "volume24h": int(volume_24h),
            "avgPositionSize": int(wallet.avg_position_size or 0),
            "lastTradeAge": last_trade_age,
            "isActive": wallet.is_active,
            "riskAlert": roi_7d < -10  # Alert if losing >10% this week
        })
    
    # === ACTIVE POSITIONS ===
    open_positions = db.query(Position).filter(
        Position.status == "open"
    ).order_by(desc(Position.entry_time)).all()
    
    positions = []
    for pos in open_positions[:20]:  # Limit to 20 most recent
        # Calculate current P/L (mock current price for now)
        entry_price = pos.entry_price or 0.0
        current_price = entry_price * 1.05  # TODO: fetch real current price from Polymarket API
        pnl = (current_price - entry_price) * (pos.size or 0)
        if pos.side == "NO":
            pnl = -pnl
        
        age_seconds = int((now - pos.entry_time).total_seconds())
        
        positions.append({
            "id": f"pos_{pos.id}",
            "market": pos.market_name or "Unknown Market",
            "side": pos.side or "YES",
            "entryPrice": round(entry_price, 2),
            "currentPrice": round(current_price, 2),
            "pnl": round(pnl, 2),
            "probability": round(current_price, 2),  # Current price = probability
            "ageSeconds": age_seconds,
            "slippage": round((pos.slippage or 0) * 100, 1),
            "canCashOut": True
        })
    
    # === RISK SETTINGS ===
    # TODO: Load from config or DB
    risk_settings = {
        "positionSizing": {"mode": "fixed", "amount": 500},
        "maxSlippage": 2.0,
        "gasLimit": 100,
        "stopLoss": {"enabled": True, "dailyLimit": -200, "perTrade": -15}
    }
    
    # === ALERTS (Recent trades/events) ===
    recent_trades = db.query(Trade).order_by(desc(Trade.entry_time)).limit(10).all()
    alerts = []
    
    for trade in recent_trades:
        if trade.exit_price:  # Closed trade
            level = "success" if (trade.profit_loss or 0) > 0 else "error"
            msg = f"{'PROFIT' if level == 'success' else 'LOSS'}: Sold {trade.side} '{trade.market_slug[:30]}' ${abs(trade.profit_loss or 0):.2f}"
        else:  # Open trade
            level = "success"
            msg = f"TRADE EXECUTED: Bought {trade.side} '{trade.market_slug[:30]}' ${trade.size or 0:.0f} @{trade.entry_price:.2f}"
        
        alerts.append({
            "timestamp": int(trade.entry_time.timestamp()),
            "level": level,
            "message": msg
        })
    
    # Add system alerts if no trades
    if not alerts:
        alerts = [
            {
                "timestamp": int(now.timestamp()) - 60,
                "level": "warning",
                "message": "No recent trades found. Start bot with: python main.py"
            }
        ]
    
    return {
        "liveStatus": live_status,
        "targets": targets,
        "positions": positions,
        "riskSettings": risk_settings,
        "alerts": alerts
    }
