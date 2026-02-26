"""Wallets endpoints - Tracked insider wallets."""
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from api.deps import get_db_session
from api.models import WalletsListResponse, WalletResponse
from bot.database import TrackedWallet
from bot.utils.logger import logger

router = APIRouter()


@router.get("/wallets", response_model=WalletsListResponse)
async def get_wallets(
    active_only: bool = Query(False, description="Show only active wallets"),
    db: Session = Depends(get_db_session),
):
    """Get list of tracked insider wallets.
    
    Args:
        active_only: If True, return only wallets with is_active=True
    
    Returns:
        List of tracked wallets with scores, win rates, and stats.
    """
    try:
        query = db.query(TrackedWallet)
        
        if active_only:
            query = query.filter(TrackedWallet.is_active == True)  # noqa: E712
        
        wallets = query.order_by(TrackedWallet.score.desc()).all()
        
        wallets_data = [
            WalletResponse(
                address=w.address,
                label=w.label,
                score=w.score or 0.0,
                win_rate=w.win_rate or 0.0,
                total_trades=w.total_trades or 0,
                total_profit_usd=w.total_profit_usd or 0.0,
                is_active=w.is_active or False,
                is_whale=w.is_whale or False,
                consecutive_losses=getattr(w, "consecutive_losses", 0) or 0,
                entry_timing_score=getattr(w, "entry_timing_score", 0.5) or 0.5,
                first_seen=w.first_seen,
                last_activity=w.last_activity,
            )
            for w in wallets
        ]
        
        active_count = sum(1 for w in wallets_data if w.is_active)
        
        return WalletsListResponse(
            wallets=wallets_data,
            total_count=len(wallets_data),
            active_count=active_count,
        )
    except Exception as e:
        logger.error(f"[API] /wallets error: {e}")
        return WalletsListResponse(wallets=[], total_count=0, active_count=0)
