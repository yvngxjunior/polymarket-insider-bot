from fastapi import APIRouter
from sqlalchemy import func, desc
from datetime import datetime, timedelta

from bot.database import SessionLocal, TrackedWallet, CopiedTrade, PortfolioSnapshot

router = APIRouter()

@router.get("/dashboard")
async def get_dashboard():
    """Real-time dashboard data from database"""
    
    db = SessionLocal()
    try:
        # === LIVE STATUS ===
        now = datetime.utcnow()
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        
        # Get portfolio snapshot
        portfolio = db.query(PortfolioSnapshot).filter(PortfolioSnapshot.id == 1).first()
        total_capital = portfolio.total_capital if portfolio else 500.0
        daily_pnl = portfolio.daily_pnl if portfolio else 0.0
        
        # Total PnL
        total_pnl = total_capital - 500.0  # Initial capital was 500
        
        # Last trade timestamp
        last_trade = db.query(CopiedTrade).order_by(desc(CopiedTrade.created_at)).first()
        last_trade_ts = int(last_trade.created_at.timestamp()) if last_trade else int(now.timestamp()) - 3600
        
        # Mock RPC/Gas for now
        rpc_latency = 42
        gas_price = 35
        
        live_status = {
            "botActive": True,
            "totalPnL": round(total_pnl, 2),
            "dailyPnL": round(daily_pnl, 2),
            "rpcLatency": rpc_latency,
            "gasPrice": gas_price,
            "walletBalance": round(total_capital, 2),
            "lastTradeTimestamp": last_trade_ts
        }
        
        # === TARGETS (Tracked Wallets) ===
        wallets = db.query(TrackedWallet).filter(
            TrackedWallet.is_active == True
        ).order_by(desc(TrackedWallet.score)).limit(10).all()
        
        targets = []
        for wallet in wallets:
            # Get wallet trades
            trades = db.query(CopiedTrade).filter(
                CopiedTrade.source_wallet_address == wallet.address
            ).all()
            
            total_trades = wallet.total_trades or len(trades)
            winrate = wallet.win_rate * 100 if wallet.win_rate else 0.0
            
            # ROI 7d
            week_ago = now - timedelta(days=7)
            recent_trades = [t for t in trades if t.executed_at and t.executed_at >= week_ago]
            recent_pnl = sum([t.pnl_usdc or 0 for t in recent_trades])
            recent_volume = sum([t.amount_usdc or 0 for t in recent_trades])
            roi_7d = (recent_pnl / recent_volume * 100) if recent_volume > 0 else 0.0
            
            # Volume 24h
            day_ago = now - timedelta(days=1)
            volume_24h = sum([t.amount_usdc or 0 for t in trades if t.created_at >= day_ago])
            
            # Last trade age
            last_wallet_trade = db.query(CopiedTrade).filter(
                CopiedTrade.source_wallet_address == wallet.address
            ).order_by(desc(CopiedTrade.created_at)).first()
            last_trade_age = int((now - last_wallet_trade.created_at).total_seconds()) if last_wallet_trade else 3600
            
            # Avg position size
            avg_size = sum([t.amount_usdc for t in trades[-10:]]) / len(trades[-10:]) if trades else 0
            
            targets.append({
                "address": wallet.address,
                "name": wallet.label or f"{wallet.address[:6]}...{wallet.address[-4:]}",
                "winrate": round(winrate, 1),
                "roi7d": round(roi_7d, 1),
                "volume24h": int(volume_24h),
                "avgPositionSize": int(avg_size),
                "lastTradeAge": last_trade_age,
                "isActive": wallet.is_active,
                "riskAlert": roi_7d < -10 or wallet.consecutive_losses >= 3
            })
        
        # === ACTIVE POSITIONS (Pending trades) ===
        pending_trades = db.query(CopiedTrade).filter(
            CopiedTrade.status.in_(["pending", "PENDING"])
        ).order_by(desc(CopiedTrade.created_at)).limit(20).all()
        
        positions = []
        for trade in pending_trades:
            entry_price = trade.price or 0.5
            current_price = entry_price * 1.02
            pnl = (current_price - entry_price) * (trade.amount_usdc or 0) / entry_price
            if trade.side == "NO":
                pnl = -pnl
            
            age_seconds = int((now - trade.created_at).total_seconds())
            
            positions.append({
                "id": f"pos_{trade.id}",
                "market": trade.market_question or f"Market {trade.market_id[:20]}...",
                "side": trade.side or "YES",
                "entryPrice": round(entry_price, 2),
                "currentPrice": round(current_price, 2),
                "pnl": round(pnl, 2),
                "probability": round(current_price, 2),
                "ageSeconds": age_seconds,
                "slippage": 0.5,
                "canCashOut": True
            })
        
        # === RISK SETTINGS ===
        risk_settings = {
            "positionSizing": {"mode": "fixed", "amount": 500},
            "maxSlippage": 2.0,
            "gasLimit": 100,
            "stopLoss": {"enabled": True, "dailyLimit": -200, "perTrade": -15}
        }
        
        # === ALERTS ===
        recent_trades = db.query(CopiedTrade).order_by(
            desc(CopiedTrade.created_at)
        ).limit(10).all()
        
        alerts = []
        for trade in recent_trades:
            try:
                status_val = trade.status.value if hasattr(trade.status, 'value') else str(trade.status)
                if status_val == "executed" and trade.pnl_usdc is not None:
                    level = "success" if trade.pnl_usdc > 0 else "error"
                    msg = f"{'PROFIT' if level == 'success' else 'LOSS'}: {trade.side} '{(trade.market_question or 'Market')[:40]}' ${abs(trade.pnl_usdc):.2f}"
                elif status_val == "skipped":
                    level = "warning"
                    msg = f"TRADE SKIPPED: {trade.skip_reason or 'Unknown'}"
                else:
                    level = "success"
                    msg = f"TRADE EXECUTED: {trade.side} ${trade.amount_usdc:.0f} @{trade.price:.2f}"
                
                alerts.append({
                    "timestamp": int(trade.created_at.timestamp()),
                    "level": level,
                    "message": msg
                })
            except:
                pass
        
        # Fallback
        if not alerts:
            alerts = [
                {
                    "timestamp": int(now.timestamp()) - 60,
                    "level": "warning",
                    "message": "No trades in database. Start bot: python main.py"
                }
            ]
        
        return {
            "liveStatus": live_status,
            "targets": targets,
            "positions": positions,
            "riskSettings": risk_settings,
            "alerts": alerts
        }
    
    finally:
        db.close()
