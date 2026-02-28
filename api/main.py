"""
FastAPI Server v1.0
====================
Serveur API REST + WebSocket pour PolyInsider Bot.

Lancer:
    uvicorn api.main:app --reload --port 8000

Docs:
    http://localhost:8000/docs
"""
import asyncio
from typing import List, Optional
from datetime import datetime, timedelta

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from bot.database import get_db, TrackedWallet, CopiedTrade, PortfolioSnapshot
from bot.analytics.backtest import run_backtest, BacktestResult
from bot.config import get_settings
from bot.utils.logger import logger

settings = get_settings()

app = FastAPI(
    title="PolyInsider Bot API",
    description="API REST pour contrôler le bot Polymarket copy trading",
    version="1.0.0",
)

# CORS pour frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # En prod: spécifier domaine exact
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# WebSocket connections pool
active_connections: List[WebSocket] = []


# ========== MODELS ==========

class HealthResponse(BaseModel):
    status: str
    dry_run: bool
    uptime_seconds: float
    version: str


class PositionResponse(BaseModel):
    token_id: str
    market_question: str
    side: str
    entry_price: float
    amount_usdc: float
    current_pnl_usdc: Optional[float]
    created_at: str


class PortfolioResponse(BaseModel):
    total_capital: float
    peak_capital: float
    daily_pnl: float
    total_pnl: float
    open_positions_count: int
    updated_at: str


class TradeResponse(BaseModel):
    id: int
    source_wallet: str
    market_question: Optional[str]
    token_id: str
    side: str
    amount_usdc: float
    price: float
    pnl_usdc: Optional[float]
    status: str
    created_at: str


class WalletResponse(BaseModel):
    address: str
    label: Optional[str]
    win_rate: float
    total_trades: int
    score: float
    is_active: bool
    last_activity: str


class AddWalletRequest(BaseModel):
    address: str
    label: Optional[str] = None


class SettingsResponse(BaseModel):
    dry_run: bool
    max_trade_amount: float
    min_win_rate: float
    scan_interval: int
    whale_threshold: float
    initial_capital: float


class UpdateSettingsRequest(BaseModel):
    max_trade_amount: Optional[float] = None
    min_win_rate: Optional[float] = None
    whale_threshold: Optional[float] = None


class BotControlResponse(BaseModel):
    status: str
    message: str


class BacktestRequest(BaseModel):
    start_date: str  # YYYY-MM-DD
    end_date: str
    initial_capital: float = 500.0


# ========== ENDPOINTS ==========

@app.get("/api/health", response_model=HealthResponse)
async def get_health():
    """Status santé du bot."""
    return HealthResponse(
        status="running",
        dry_run=settings.dry_run,
        uptime_seconds=0.0,  # TODO: implémenter uptime tracker
        version="3.1.0",
    )


@app.get("/api/positions", response_model=List[PositionResponse])
async def get_positions():
    """Liste toutes les positions ouvertes."""
    with get_db() as db:
        trades = db.query(CopiedTrade).filter(
            CopiedTrade.status == "executed",
            CopiedTrade.pnl_usdc == None,  # noqa: E711
        ).order_by(CopiedTrade.created_at.desc()).limit(50).all()
        
        return [
            PositionResponse(
                token_id=t.token_id,
                market_question=t.market_question or "Unknown",
                side=t.side,
                entry_price=t.price,
                amount_usdc=t.amount_usdc,
                current_pnl_usdc=None,  # TODO: fetch current price
                created_at=t.created_at.isoformat(),
            )
            for t in trades
        ]


@app.get("/api/portfolio", response_model=PortfolioResponse)
async def get_portfolio():
    """Snapshot portfolio actuel."""
    with get_db() as db:
        snapshot = db.query(PortfolioSnapshot).filter(
            PortfolioSnapshot.id == 1
        ).first()
        
        if not snapshot:
            raise HTTPException(status_code=404, detail="Portfolio snapshot not found")
        
        # Compte positions ouvertes
        open_count = db.query(CopiedTrade).filter(
            CopiedTrade.status == "executed",
            CopiedTrade.pnl_usdc == None,  # noqa: E711
        ).count()
        
        total_pnl = snapshot.total_capital - settings.initial_capital
        
        return PortfolioResponse(
            total_capital=snapshot.total_capital,
            peak_capital=snapshot.peak_capital,
            daily_pnl=snapshot.daily_pnl,
            total_pnl=total_pnl,
            open_positions_count=open_count,
            updated_at=snapshot.updated_at.isoformat(),
        )


@app.get("/api/trades", response_model=List[TradeResponse])
async def get_trades(
    limit: int = Query(50, ge=1, le=500),
    status: Optional[str] = None,
):
    """Historique des trades."""
    with get_db() as db:
        query = db.query(CopiedTrade)
        
        if status:
            query = query.filter(CopiedTrade.status == status)
        
        trades = query.order_by(
            CopiedTrade.created_at.desc()
        ).limit(limit).all()
        
        return [
            TradeResponse(
                id=t.id,
                source_wallet=t.source_wallet_address[:10] + "...",
                market_question=t.market_question,
                token_id=t.token_id,
                side=t.side,
                amount_usdc=t.amount_usdc,
                price=t.price,
                pnl_usdc=t.pnl_usdc,
                status=t.status.value if hasattr(t.status, 'value') else str(t.status),
                created_at=t.created_at.isoformat(),
            )
            for t in trades
        ]


@app.get("/api/wallets", response_model=List[WalletResponse])
async def get_wallets(active_only: bool = True):
    """Liste wallets trackés."""
    with get_db() as db:
        query = db.query(TrackedWallet)
        
        if active_only:
            query = query.filter(TrackedWallet.is_active == True)  # noqa: E712
        
        wallets = query.order_by(TrackedWallet.score.desc()).all()
        
        return [
            WalletResponse(
                address=w.address,
                label=w.label,
                win_rate=w.win_rate or 0.0,
                total_trades=w.total_trades or 0,
                score=w.score or 0.0,
                is_active=w.is_active,
                last_activity=w.last_activity.isoformat() if w.last_activity else "",
            )
            for w in wallets
        ]


@app.post("/api/wallets", response_model=WalletResponse)
async def add_wallet(request: AddWalletRequest):
    """Ajoute un wallet à la whitelist."""
    with get_db() as db:
        # Vérifie si existe déjà
        existing = db.query(TrackedWallet).filter(
            TrackedWallet.address == request.address
        ).first()
        
        if existing:
            raise HTTPException(status_code=400, detail="Wallet already tracked")
        
        # Crée nouveau wallet
        wallet = TrackedWallet(
            address=request.address,
            label=request.label,
            score=1.0,  # Whitelist = score max
            is_active=True,
            win_rate=0.70,
            total_trades=0,
            first_seen=datetime.utcnow(),
            last_activity=datetime.utcnow(),
        )
        db.add(wallet)
        db.commit()
        db.refresh(wallet)
        
        # Ajoute à la whitelist .env (méthode à implémenter)
        logger.info(f"[API] Added wallet {request.address[:10]}... to whitelist")
        
        return WalletResponse(
            address=wallet.address,
            label=wallet.label,
            win_rate=wallet.win_rate,
            total_trades=wallet.total_trades,
            score=wallet.score,
            is_active=wallet.is_active,
            last_activity=wallet.last_activity.isoformat(),
        )


@app.get("/api/settings", response_model=SettingsResponse)
async def get_settings_endpoint():
    """Config risk actuelle."""
    return SettingsResponse(
        dry_run=settings.dry_run,
        max_trade_amount=settings.max_trade_amount,
        min_win_rate=settings.min_win_rate,
        scan_interval=settings.scan_interval,
        whale_threshold=settings.whale_threshold,
        initial_capital=settings.initial_capital,
    )


@app.patch("/api/settings", response_model=SettingsResponse)
async def update_settings(request: UpdateSettingsRequest):
    """Update config risk (nécessite redémarrage bot)."""
    # TODO: Implémenter persistence dans .env ou DB
    # Pour l'instant, update en mémoire seulement
    
    if request.max_trade_amount is not None:
        settings.max_trade_amount = request.max_trade_amount
    if request.min_win_rate is not None:
        settings.min_win_rate = request.min_win_rate
    if request.whale_threshold is not None:
        settings.whale_threshold = request.whale_threshold
    
    logger.info(f"[API] Settings updated: {request.dict(exclude_unset=True)}")
    
    return SettingsResponse(
        dry_run=settings.dry_run,
        max_trade_amount=settings.max_trade_amount,
        min_win_rate=settings.min_win_rate,
        scan_interval=settings.scan_interval,
        whale_threshold=settings.whale_threshold,
        initial_capital=settings.initial_capital,
    )


@app.post("/api/bot/start", response_model=BotControlResponse)
async def start_bot():
    """Démarre le bot (si arrêté)."""
    # TODO: Implémenter contrôle d'état bot
    logger.info("[API] Bot start requested")
    return BotControlResponse(
        status="starting",
        message="Bot démarrage en cours...",
    )


@app.post("/api/bot/stop", response_model=BotControlResponse)
async def stop_bot():
    """Arrête le bot gracefully."""
    # TODO: Implémenter signal shutdown
    logger.info("[API] Bot stop requested")
    return BotControlResponse(
        status="stopping",
        message="Bot arrêt en cours...",
    )


@app.post("/api/backtest")
async def run_backtest_endpoint(request: BacktestRequest):
    """Lance un backtest sur période donnée."""
    try:
        result = await run_backtest(
            start_date=request.start_date,
            end_date=request.end_date,
            initial_capital=request.initial_capital,
        )
        return result.to_dict()
    except Exception as e:
        logger.error(f"[API] Backtest error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ========== WEBSOCKET ==========

@app.websocket("/ws/trades")
async def websocket_endpoint(websocket: WebSocket):
    """WebSocket feed pour trades temps réel."""
    await websocket.accept()
    active_connections.append(websocket)
    logger.info(f"[WS] Client connected. Total: {len(active_connections)}")
    
    try:
        while True:
            # Heartbeat pour garder connexion alive
            await asyncio.sleep(30)
            await websocket.send_json({"type": "heartbeat", "timestamp": datetime.utcnow().isoformat()})
    except WebSocketDisconnect:
        active_connections.remove(websocket)
        logger.info(f"[WS] Client disconnected. Total: {len(active_connections)}")


async def broadcast_trade(trade_data: dict):
    """Broadcast trade à tous les clients WebSocket connectés."""
    for connection in active_connections:
        try:
            await connection.send_json({
                "type": "trade",
                "data": trade_data,
                "timestamp": datetime.utcnow().isoformat(),
            })
        except Exception as e:
            logger.warning(f"[WS] Broadcast error: {e}")


# ========== STARTUP ==========

@app.on_event("startup")
async def startup_event():
    logger.info("[API] FastAPI server starting...")
    logger.info(f"[API] Docs available at http://localhost:8000/docs")


@app.on_event("shutdown")
async def shutdown_event():
    logger.info("[API] FastAPI server shutting down...")
    # Close all WebSocket connections
    for connection in active_connections:
        await connection.close()
