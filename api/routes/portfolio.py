"""Portfolio endpoint - Capital, P&L, drawdown."""
from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session

from api.deps import get_db_session
from api.models import PortfolioResponse
from bot.config import get_settings
from bot.utils.logger import logger

settings = get_settings()

router = APIRouter()


@router.get("/portfolio", response_model=PortfolioResponse)
async def get_portfolio(db: Session = Depends(get_db_session)):
    """Get current portfolio state (capital, P&L, drawdown).
    
    Returns:
        Portfolio snapshot from portfolio_snapshot table.
    """
    try:
        row = db.execute(
            text(
                "SELECT total_capital, peak_capital, daily_pnl, "
                "daily_reset_date, open_positions_csv "
                "FROM portfolio_snapshot WHERE id=1"
            )
        ).fetchone()
        
        if not row:
            # Fallback if DB not initialized
            return PortfolioResponse(
                total_capital=settings.initial_capital,
                peak_capital=settings.initial_capital,
                daily_pnl=0.0,
                drawdown_pct=0.0,
                open_positions_count=0,
                daily_reset_date="1970-01-01",
            )
        
        total_cap = float(row[0] or settings.initial_capital)
        peak_cap = float(row[1] or total_cap)
        daily_pnl = float(row[2] or 0.0)
        daily_reset = str(row[3] or "1970-01-01")
        open_csv = row[4] or ""
        
        open_count = len([t for t in open_csv.split(",") if t.strip()])
        drawdown = (peak_cap - total_cap) / peak_cap if peak_cap > 0 else 0.0
        
        return PortfolioResponse(
            total_capital=round(total_cap, 2),
            peak_capital=round(peak_cap, 2),
            daily_pnl=round(daily_pnl, 2),
            drawdown_pct=round(drawdown, 4),
            open_positions_count=open_count,
            daily_reset_date=daily_reset,
        )
    except Exception as e:
        logger.error(f"[API] /portfolio error: {e}")
        return PortfolioResponse(
            total_capital=settings.initial_capital,
            peak_capital=settings.initial_capital,
            daily_pnl=0.0,
            drawdown_pct=0.0,
            open_positions_count=0,
            daily_reset_date="1970-01-01",
        )
