"""PolyInsider API v1.0 - REST + WebSocket"""
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
import asyncio
from datetime import datetime

from bot.config import get_settings
from bot.database import get_db, TrackedWallet, Trade, Position
from bot.analytics.backtest import BacktestEngine
from bot.utils.logger import logger

settings = get_settings()

app = FastAPI(
    title="PolyInsider Bot API",
    version="1.0.0",
    description="REST API for Polymarket Insider Trading Bot",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # TODO: Restrict to frontend domain
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ============================================================================
# Models
# ============================================================================

class WalletInput(BaseModel):
    address: str = Field(..., min_length=42, max_length=42)
    score: Optional[float] = Field(0.70, ge=0.0, le=1.0)

class BacktestRequest(BaseModel):
    start_date: str = Field(..., description="ISO format: 2026-01-01")
    end_date: str = Field(..., description="ISO format: 2026-02-28")
    initial_capital: float = Field(1000.0, gt=0)
    wallet_addresses: Optional[List[str]] = None

class BotControlRequest(BaseModel):
    action: str = Field(..., description="start|stop|status")

# ============================================================================
# Endpoints
# ============================================================================

@app.get("/")
async def root():
    return {
        "service": "PolyInsider Bot API",
        "version": "1.0.0",
        "status": "running",
        "docs": "/docs",
    }

@app.get("/api/health")
async def health_check():
    """Health check endpoint"""
    return {"status": "healthy", "timestamp": datetime.utcnow().isoformat()}

# ----------------------------------------------------------------------------
# Portfolio & Positions
# ----------------------------------------------------------------------------

@app.get("/api/portfolio")
async def get_portfolio() -> Dict[str, Any]:
    """Get current portfolio summary"""
    with get_db() as db:
        # Get total capital from latest snapshot
        from bot.database import PortfolioSnapshot
        latest_snapshot = (
            db.query(PortfolioSnapshot)
            .order_by(PortfolioSnapshot.timestamp.desc())
            .first()
        )
        
        total_capital = (
            float(latest_snapshot.total_capital)
            if latest_snapshot
            else settings.initial_capital
        )
        
        # Get open positions count
        open_positions = db.query(Position).filter(
            Position.status == "OPEN"
        ).count()
        
        # Calculate total PnL from closed positions
        closed_trades = db.query(Trade).filter(
            Trade.pnl_usdc.isnot(None)
        ).all()
        
        total_pnl = sum(float(t.pnl_usdc) for t in closed_trades if t.pnl_usdc)
        
    return {
        "total_capital": round(total_capital, 2),
        "initial_capital": settings.initial_capital,
        "total_pnl": round(total_pnl, 2),
        "open_positions": open_positions,
        "return_pct": round(
            ((total_capital - settings.initial_capital) / settings.initial_capital) * 100,
            2,
        ),
    }

@app.get("/api/positions")
async def get_positions(status: Optional[str] = None) -> Dict[str, Any]:
    """Get positions (open/closed)"""
    with get_db() as db:
        query = db.query(Position)
        
        if status:
            query = query.filter(Position.status == status.upper())
            
        positions = query.order_by(Position.opened_at.desc()).limit(50).all()
        
    return {
        "positions": [
            {
                "id": p.id,
                "token_id": p.token_id,
                "entry_price": float(p.entry_price),
                "amount_usdc": float(p.amount_usdc),
                "side": p.side,
                "status": p.status,
                "pnl_usdc": float(p.pnl_usdc) if p.pnl_usdc else None,
                "opened_at": p.opened_at.isoformat() if p.opened_at else None,
                "closed_at": p.closed_at.isoformat() if p.closed_at else None,
                "market_question": p.market_question,
            }
            for p in positions
        ],
        "total": len(positions),
    }

# ----------------------------------------------------------------------------
# Wallets Management
# ----------------------------------------------------------------------------

@app.get("/api/wallets")
async def get_wallets() -> Dict[str, Any]:
    """Get tracked wallets"""
    with get_db() as db:
        active_wallets = (
            db.query(TrackedWallet)
            .filter(TrackedWallet.is_active == True)  # noqa: E712
            .order_by(TrackedWallet.score.desc())
            .all()
        )
        
    whitelist = settings.get_whitelist()
    blacklist = settings.get_blacklist()
    
    return {
        "active_wallets": [
            {
                "address": w.address,
                "score": float(w.score or 0),
                "total_trades": w.total_trades or 0,
                "win_rate": float(w.win_rate or 0),
                "is_whitelisted": w.address.lower() in whitelist,
            }
            for w in active_wallets
        ],
        "whitelist_count": len(whitelist),
        "blacklist_count": len(blacklist),
        "total_active": len(active_wallets),
    }

@app.post("/api/wallets/whitelist")
async def add_to_whitelist(wallet: WalletInput):
    """Add wallet to whitelist"""
    current_whitelist = settings.get_whitelist()
    
    if wallet.address.lower() in current_whitelist:
        raise HTTPException(status_code=400, detail="Wallet already whitelisted")
        
    current_whitelist.add(wallet.address.lower())
    new_whitelist_str = ",".join(current_whitelist)
    
    # Update .env (in production, use proper config management)
    logger.info(f"[API] Added {wallet.address} to whitelist")
    
    return {
        "status": "added",
        "wallet": wallet.address,
        "message": "Wallet added to whitelist (restart bot to apply)",
    }

@app.post("/api/wallets/blacklist")
async def add_to_blacklist(wallet: WalletInput):
    """Add wallet to blacklist"""
    current_blacklist = settings.get_blacklist()
    
    if wallet.address.lower() in current_blacklist:
        raise HTTPException(status_code=400, detail="Wallet already blacklisted")
        
    current_blacklist.add(wallet.address.lower())
    logger.info(f"[API] Added {wallet.address} to blacklist")
    
    return {
        "status": "added",
        "wallet": wallet.address,
        "message": "Wallet added to blacklist (restart bot to apply)",
    }

# ----------------------------------------------------------------------------
# Backtest
# ----------------------------------------------------------------------------

@app.post("/api/backtest")
async def run_backtest(request: BacktestRequest) -> Dict[str, Any]:
    """Run backtest on historical trades"""
    try:
        engine = BacktestEngine(
            start_date=request.start_date,
            end_date=request.end_date,
            initial_capital=request.initial_capital,
        )
        
        result = await engine.run(wallet_addresses=request.wallet_addresses)
        
        return {
            "success": True,
            "period": {
                "start": request.start_date,
                "end": request.end_date,
                "initial_capital": request.initial_capital,
            },
            "results": result.to_dict(),
        }
    except Exception as e:
        logger.error(f"[API] Backtest error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# ----------------------------------------------------------------------------
# Bot Control
# ----------------------------------------------------------------------------

@app.post("/api/bot/control")
async def control_bot(request: BotControlRequest):
    """Control bot (start/stop/status)"""
    # TODO: Implement actual bot control (requires refactoring main.py)
    logger.info(f"[API] Bot control: {request.action}")
    
    if request.action == "status":
        return {"status": "running", "mode": "DRY_RUN" if settings.dry_run else "LIVE"}
    elif request.action == "start":
        return {"status": "started", "message": "Bot start requested (manual restart required)"}
    elif request.action == "stop":
        return {"status": "stopped", "message": "Bot stop requested (manual kill required)"}
    else:
        raise HTTPException(status_code=400, detail="Invalid action")

# ----------------------------------------------------------------------------
# WebSocket - Live Trades Stream
# ----------------------------------------------------------------------------

class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        self.active_connections.remove(websocket)

    async def broadcast(self, message: dict):
        for connection in self.active_connections:
            try:
                await connection.send_json(message)
            except Exception:
                pass

manager = ConnectionManager()

@app.websocket("/ws/trades")
async def websocket_endpoint(websocket: WebSocket):
    """WebSocket for live trade updates"""
    await manager.connect(websocket)
    logger.info("[WS] Client connected")
    
    try:
        while True:
            # Keep connection alive + stream latest trades
            with get_db() as db:
                latest_trades = (
                    db.query(Trade)
                    .order_by(Trade.timestamp.desc())
                    .limit(5)
                    .all()
                )
                
            await websocket.send_json({
                "type": "trades_update",
                "trades": [
                    {
                        "token_id": t.token_id[:16] + "...",
                        "side": t.side,
                        "amount": float(t.amount_usdc),
                        "pnl": float(t.pnl_usdc) if t.pnl_usdc else None,
                        "timestamp": t.timestamp.isoformat() if t.timestamp else None,
                    }
                    for t in latest_trades
                ],
                "timestamp": datetime.utcnow().isoformat(),
            })
            
            await asyncio.sleep(3)
            
    except WebSocketDisconnect:
        manager.disconnect(websocket)
        logger.info("[WS] Client disconnected")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001, reload=True)
