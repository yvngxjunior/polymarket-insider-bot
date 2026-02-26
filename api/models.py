"""Pydantic response models for FastAPI routes."""
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


# ============================================================================
# Positions
# ============================================================================

class PositionResponse(BaseModel):
    """Single open position."""
    trade_id: int = Field(description="DB ID of the copied trade")
    token_id: str = Field(description="Polymarket token ID")
    market_question: str = Field(description="Market title")
    side: str = Field(description="BUY or SELL")
    entry_price: float = Field(description="Entry price (0-1)")
    current_price: Optional[float] = Field(None, description="Current market price (0-1)")
    amount_usdc: float = Field(description="Position size in USDC")
    unrealized_pnl: Optional[float] = Field(None, description="Unrealized P&L in USDC")
    tp1_hit: bool = Field(description="Take Profit 1 (50%) triggered")
    tp2_price: float = Field(description="Take Profit 2 target price")
    sl_price: float = Field(description="Stop Loss price")
    opened_at: datetime = Field(description="Position open timestamp")

    class Config:
        json_schema_extra = {
            "example": {
                "trade_id": 42,
                "token_id": "0x1234abcd...",
                "market_question": "Will Trump win 2024?",
                "side": "BUY",
                "entry_price": 0.65,
                "current_price": 0.72,
                "amount_usdc": 25.0,
                "unrealized_pnl": 2.69,
                "tp1_hit": False,
                "tp2_price": 0.85,
                "sl_price": 0.55,
                "opened_at": "2026-02-26T17:30:00Z",
            }
        }


class PositionsListResponse(BaseModel):
    """List of all open positions."""
    positions: list[PositionResponse]
    total_count: int = Field(description="Number of open positions")
    total_capital_deployed: float = Field(description="Sum of all position sizes in USDC")


# ============================================================================
# Portfolio
# ============================================================================

class PortfolioResponse(BaseModel):
    """Current portfolio state."""
    total_capital: float = Field(description="Current total capital in USDC")
    peak_capital: float = Field(description="All-time peak capital")
    daily_pnl: float = Field(description="P&L since midnight (UTC)")
    drawdown_pct: float = Field(description="Current drawdown % from peak")
    open_positions_count: int = Field(description="Number of open positions")
    daily_reset_date: str = Field(description="Date of last daily reset (ISO format)")

    class Config:
        json_schema_extra = {
            "example": {
                "total_capital": 523.45,
                "peak_capital": 550.00,
                "daily_pnl": -12.30,
                "drawdown_pct": 0.048,
                "open_positions_count": 3,
                "daily_reset_date": "2026-02-26",
            }
        }


# ============================================================================
# Trades
# ============================================================================

class TradeResponse(BaseModel):
    """Single trade (executed, skipped, or failed)."""
    id: int
    source_wallet: str = Field(description="Source wallet address (shortened)")
    market_question: Optional[str] = Field(None, description="Market title")
    token_id: str
    side: str
    amount_usdc: float
    price: float
    pnl_usdc: Optional[float] = Field(None, description="Realized P&L (closed positions only)")
    status: str = Field(description="EXECUTED, SKIPPED, FAILED")
    skip_reason: Optional[str] = Field(None, description="Why trade was skipped")
    tx_hash: Optional[str] = Field(None, description="Blockchain transaction hash")
    created_at: datetime
    executed_at: Optional[datetime] = None

    class Config:
        json_schema_extra = {
            "example": {
                "id": 123,
                "source_wallet": "0xabcd1234...",
                "market_question": "Will BTC hit 100k?",
                "token_id": "0x5678efgh...",
                "side": "BUY",
                "amount_usdc": 15.50,
                "price": 0.42,
                "pnl_usdc": 3.20,
                "status": "EXECUTED",
                "skip_reason": None,
                "tx_hash": "0x9abcdef...",
                "created_at": "2026-02-25T14:20:00Z",
                "executed_at": "2026-02-25T14:20:05Z",
            }
        }


class TradesListResponse(BaseModel):
    """Paginated list of trades."""
    trades: list[TradeResponse]
    total_count: int
    page: int
    per_page: int


# ============================================================================
# Wallets
# ============================================================================

class WalletResponse(BaseModel):
    """Tracked wallet (insider)."""
    address: str
    label: Optional[str] = None
    score: float = Field(description="Composite score (0-100)")
    win_rate: float = Field(description="Win rate (0-1)")
    total_trades: int
    total_profit_usd: float
    is_active: bool = Field(description="Currently tracked for copy trading")
    is_whale: bool
    consecutive_losses: int
    entry_timing_score: float = Field(description="Timing quality score (0-1)")
    first_seen: datetime
    last_activity: datetime

    class Config:
        json_schema_extra = {
            "example": {
                "address": "0x1a2b3c4d5e6f...",
                "label": "Whale #7",
                "score": 87.5,
                "win_rate": 0.73,
                "total_trades": 142,
                "total_profit_usd": 12450.00,
                "is_active": True,
                "is_whale": True,
                "consecutive_losses": 0,
                "entry_timing_score": 0.85,
                "first_seen": "2026-01-15T08:00:00Z",
                "last_activity": "2026-02-26T16:45:00Z",
            }
        }


class WalletsListResponse(BaseModel):
    """List of tracked wallets."""
    wallets: list[WalletResponse]
    total_count: int
    active_count: int = Field(description="Number of active wallets being copied")
