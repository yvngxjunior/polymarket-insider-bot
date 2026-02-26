"""Trades endpoints - History of executed/skipped/failed trades."""
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from api.deps import get_db_session
from api.models import TradesListResponse, TradeResponse
from bot.database import CopiedTrade
from bot.utils.logger import logger

router = APIRouter()


@router.get("/trades", response_model=TradesListResponse)
async def get_trades(
    page: int = Query(1, ge=1, description="Page number"),
    per_page: int = Query(50, ge=1, le=100, description="Items per page"),
    status: str | None = Query(None, description="Filter by status (EXECUTED, SKIPPED, FAILED)"),
    db: Session = Depends(get_db_session),
):
    """Get paginated trade history.
    
    Args:
        page: Page number (1-indexed)
        per_page: Results per page (max 100)
        status: Optional filter by trade status
    
    Returns:
        Paginated list of trades from copied_trades table.
    """
    try:
        query = db.query(CopiedTrade)
        
        if status:
            query = query.filter(CopiedTrade.status == status.upper())
        
        total = query.count()
        
        trades = (
            query.order_by(CopiedTrade.created_at.desc())
            .offset((page - 1) * per_page)
            .limit(per_page)
            .all()
        )
        
        trades_data = [
            TradeResponse(
                id=t.id,
                source_wallet=t.source_wallet_address[:10] + "..." if t.source_wallet_address else "?",
                market_question=t.market_question,
                token_id=t.token_id,
                side=t.side,
                amount_usdc=t.amount_usdc,
                price=t.price,
                pnl_usdc=t.pnl_usdc,
                status=t.status.value if hasattr(t.status, "value") else str(t.status),
                skip_reason=t.skip_reason,
                tx_hash=t.tx_hash,
                created_at=t.created_at,
                executed_at=t.executed_at,
            )
            for t in trades
        ]
        
        return TradesListResponse(
            trades=trades_data,
            total_count=total,
            page=page,
            per_page=per_page,
        )
    except Exception as e:
        logger.error(f"[API] /trades error: {e}")
        return TradesListResponse(trades=[], total_count=0, page=page, per_page=per_page)
