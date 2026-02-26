"""Positions endpoints - Open trades with TP/SL tracking."""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from api.deps import get_db_session
from api.models import PositionsListResponse, PositionResponse
from bot.trading.position_manager import PositionManager
from bot.utils.logger import logger

router = APIRouter()


@router.get("/positions", response_model=PositionsListResponse)
async def get_positions(db: Session = Depends(get_db_session)):
    """Get all open positions with TP/SL status.
    
    Returns:
        List of open positions with unrealized P&L, TP1/TP2/SL prices.
    """
    try:
        # Read from PositionManager in-memory state
        # Note: PositionManager is singleton-like, instantiate to read state
        from bot.trading.polymarket import PolymarketDataClient
        from bot.trading.risk import RiskManager
        from bot.notifications.telegram import TelegramNotifier
        
        client = PolymarketDataClient()
        risk = RiskManager()
        notifier = TelegramNotifier()
        pm = PositionManager(client=client, risk_manager=risk, notifier=notifier)
        
        positions_data = []
        total_deployed = 0.0
        
        for token_id, pos in pm._positions.items():
            # Fetch current price (if available)
            current_price = None
            unrealized_pnl = None
            try:
                # Simple price fetch from CLOB (no complex logic)
                # This is a read-only operation, safe to call
                pass  # TODO: implement _fetch_current_price() helper
            except Exception:
                pass
            
            positions_data.append(
                PositionResponse(
                    trade_id=pos.trade_id,
                    token_id=pos.token_id,
                    market_question=pos.market_question,
                    side=pos.side,
                    entry_price=pos.entry_price,
                    current_price=current_price,
                    amount_usdc=pos.amount_usdc,
                    unrealized_pnl=unrealized_pnl,
                    tp1_hit=pos.tp1_hit,
                    tp2_price=pos.tp2_price,
                    sl_price=pos.sl_price,
                    opened_at=pos.opened_at,
                )
            )
            total_deployed += pos.amount_usdc
        
        return PositionsListResponse(
            positions=positions_data,
            total_count=len(positions_data),
            total_capital_deployed=round(total_deployed, 2),
        )
    except Exception as e:
        logger.error(f"[API] /positions error: {e}")
        return PositionsListResponse(positions=[], total_count=0, total_capital_deployed=0.0)
