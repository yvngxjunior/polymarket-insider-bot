"""Portfolio and positions API endpoints."""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime

router = APIRouter(prefix="/api", tags=["portfolio"])


class PortfolioStats(BaseModel):
    """Portfolio statistics model."""
    total_capital: float
    peak_capital: float
    daily_pnl: float
    total_pnl: float
    win_rate: float
    total_trades: int
    winning_trades: int
    losing_trades: int
    open_positions: int
    avg_win: float
    avg_loss: float
    largest_win: float
    largest_loss: float


class Position(BaseModel):
    """Open position model."""
    id: int
    market_question: str
    token_id: str
    side: str
    amount_usdc: float
    entry_price: float
    current_price: Optional[float] = None
    pnl_usdc: Optional[float] = None
    pnl_pct: Optional[float] = None
    executed_at: datetime
    age_hours: float
    source_wallet: str


def get_mock_portfolio() -> PortfolioStats:
    """Return mock portfolio data when bot is not configured."""
    return PortfolioStats(
        total_capital=500.0,
        peak_capital=500.0,
        daily_pnl=0.0,
        total_pnl=0.0,
        win_rate=0.0,
        total_trades=0,
        winning_trades=0,
        losing_trades=0,
        open_positions=0,
        avg_win=0.0,
        avg_loss=0.0,
        largest_win=0.0,
        largest_loss=0.0,
    )


def get_portfolio_from_db() -> PortfolioStats:
    """Calculate portfolio stats from database."""
    try:
        # Lazy import to avoid .env validation at startup
        from pathlib import Path
        import sys
        bot_root = Path(__file__).parent.parent.parent.parent
        sys.path.insert(0, str(bot_root))
        
        from bot.database import get_db, CopiedTrade, TradeStatus
        from bot.config import get_settings
        
        settings = get_settings()
        
        with get_db() as db:
            # Get all executed trades
            all_trades = db.query(CopiedTrade).filter(
                CopiedTrade.status == TradeStatus.EXECUTED
            ).all()
            
            if not all_trades:
                return PortfolioStats(
                    total_capital=settings.initial_capital,
                    peak_capital=settings.initial_capital,
                    daily_pnl=0.0,
                    total_pnl=0.0,
                    win_rate=0.0,
                    total_trades=0,
                    winning_trades=0,
                    losing_trades=0,
                    open_positions=0,
                    avg_win=0.0,
                    avg_loss=0.0,
                    largest_win=0.0,
                    largest_loss=0.0,
                )
            
            # Count open positions (not closed)
            open_positions = len([
                t for t in all_trades
                if not t.skip_reason or "CLOSED" not in t.skip_reason.upper()
            ])
            
            # Calculate PnL from closed trades
            closed_trades = [
                t for t in all_trades
                if t.skip_reason and ("CLOSED" in t.skip_reason.upper() or "TP" in t.skip_reason.upper())
            ]
            
            wins = [t for t in closed_trades if t.pnl_usdc and t.pnl_usdc > 0]
            losses = [t for t in closed_trades if t.pnl_usdc and t.pnl_usdc < 0]
            
            total_pnl = sum(t.pnl_usdc or 0.0 for t in closed_trades)
            total_capital = settings.initial_capital + total_pnl
            
            win_rate = len(wins) / len(closed_trades) if closed_trades else 0.0
            avg_win = sum(t.pnl_usdc for t in wins) / len(wins) if wins else 0.0
            avg_loss = sum(t.pnl_usdc for t in losses) / len(losses) if losses else 0.0
            largest_win = max((t.pnl_usdc for t in wins), default=0.0)
            largest_loss = min((t.pnl_usdc for t in losses), default=0.0)
            
            # Daily PnL (trades from today)
            today = datetime.utcnow().date()
            daily_trades = [
                t for t in closed_trades
                if t.executed_at and t.executed_at.date() == today
            ]
            daily_pnl = sum(t.pnl_usdc or 0.0 for t in daily_trades)
            
            return PortfolioStats(
                total_capital=round(total_capital, 2),
                peak_capital=round(max(total_capital, settings.initial_capital), 2),
                daily_pnl=round(daily_pnl, 2),
                total_pnl=round(total_pnl, 2),
                win_rate=round(win_rate, 4),
                total_trades=len(closed_trades),
                winning_trades=len(wins),
                losing_trades=len(losses),
                open_positions=open_positions,
                avg_win=round(avg_win, 2),
                avg_loss=round(avg_loss, 2),
                largest_win=round(largest_win, 2),
                largest_loss=round(largest_loss, 2),
            )
    
    except ImportError:
        # Bot modules not available
        return get_mock_portfolio()
    except Exception as e:
        # Bot not configured (.env missing required fields)
        print(f"Warning: Bot not configured, returning mock data. Error: {e}")
        return get_mock_portfolio()


def get_open_positions_from_db() -> List[Position]:
    """Get list of open positions from database."""
    try:
        # Lazy import
        from pathlib import Path
        import sys
        bot_root = Path(__file__).parent.parent.parent.parent
        sys.path.insert(0, str(bot_root))
        
        from bot.database import get_db, CopiedTrade, TradeStatus
        
        with get_db() as db:
            # Get trades that are not closed
            open_trades = db.query(CopiedTrade).filter(
                CopiedTrade.status == TradeStatus.EXECUTED
            ).all()
            
            open_trades = [
                t for t in open_trades
                if not t.skip_reason or "CLOSED" not in t.skip_reason.upper()
            ]
            
            positions = []
            for trade in open_trades:
                age_hours = 0.0
                if trade.executed_at:
                    age_hours = (datetime.utcnow() - trade.executed_at).total_seconds() / 3600
                
                positions.append(Position(
                    id=trade.id,
                    market_question=trade.market_question or "Unknown Market",
                    token_id=trade.token_id or "N/A",
                    side=trade.side or "BUY",
                    amount_usdc=round(trade.amount_usdc or 0.0, 2),
                    entry_price=round(trade.price or 0.0, 4),
                    current_price=None,  # Would need to fetch from Polymarket API
                    pnl_usdc=round(trade.pnl_usdc or 0.0, 2),
                    pnl_pct=round(trade.pnl_pct or 0.0, 4),
                    executed_at=trade.executed_at or datetime.utcnow(),
                    age_hours=round(age_hours, 1),
                    source_wallet=trade.source_wallet[:10] if trade.source_wallet else "N/A",
                ))
            
            return positions
    
    except ImportError:
        # Bot modules not available
        return []
    except Exception as e:
        # Bot not configured or DB error
        print(f"Warning: Could not fetch positions. Error: {e}")
        return []


@router.get("/portfolio", response_model=PortfolioStats)
async def get_portfolio() -> PortfolioStats:
    """Get current portfolio statistics.
    
    Returns capital, PnL, win rate, and performance metrics.
    If bot is not configured, returns mock data.
    """
    return get_portfolio_from_db()


@router.get("/positions", response_model=List[Position])
async def get_positions() -> List[Position]:
    """Get list of currently open positions.
    
    Returns all positions that haven't been closed yet.
    If bot is not configured, returns empty list.
    """
    return get_open_positions_from_db()
