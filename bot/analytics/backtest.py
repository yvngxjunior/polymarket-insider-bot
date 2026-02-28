"""Backtest Engine v1.0 - Replay historical trades with Kelly/TP-SL"""
from datetime import datetime
from typing import List, Dict, Any, Optional
import pandas as pd

from bot.config import get_settings
from bot.database import get_db, Trade
from bot.trading.sizing import PositionSizer
from bot.utils.logger import logger

settings = get_settings()


class BacktestResult:
    """Results from backtest run"""
    def __init__(self):
        self.total_trades = 0
        self.winning_trades = 0
        self.losing_trades = 0
        self.total_pnl = 0.0
        self.total_return_pct = 0.0
        self.win_rate = 0.0
        self.sharpe_ratio = 0.0
        self.max_drawdown = 0.0
        self.max_drawdown_pct = 0.0
        self.avg_win = 0.0
        self.avg_loss = 0.0
        self.profit_factor = 0.0
        self.trades_per_day = 0.0
        
    def to_dict(self) -> Dict[str, Any]:
        return {
            'total_trades': self.total_trades,
            'winning_trades': self.winning_trades,
            'losing_trades': self.losing_trades,
            'total_pnl_usdc': round(self.total_pnl, 2),
            'total_return_pct': round(self.total_return_pct * 100, 2),
            'win_rate': round(self.win_rate * 100, 2),
            'sharpe_ratio': round(self.sharpe_ratio, 3),
            'max_drawdown': round(self.max_drawdown, 2),
            'max_drawdown_pct': round(self.max_drawdown_pct * 100, 2),
            'avg_win_usdc': round(self.avg_win, 2),
            'avg_loss_usdc': round(self.avg_loss, 2),
            'profit_factor': round(self.profit_factor, 2),
            'trades_per_day': round(self.trades_per_day, 2),
        }


class BacktestEngine:
    """Backtesting engine for strategy validation"""
    
    def __init__(
        self,
        start_date: str,
        end_date: str,
        initial_capital: float = 1000.0,
    ):
        self.start_date = datetime.fromisoformat(start_date)
        self.end_date = datetime.fromisoformat(end_date)
        self.initial_capital = initial_capital
        self.current_capital = initial_capital
        self.peak_capital = initial_capital
        
    async def run(
        self,
        wallet_addresses: Optional[List[str]] = None,
    ) -> BacktestResult:
        """Run backtest on historical trades"""
        logger.info(
            f"[BACKTEST] Running from {self.start_date.date()} to {self.end_date.date()} "
            f"with ${self.initial_capital} capital"
        )
        
        result = BacktestResult()
        
        # Fetch historical trades from database
        with get_db() as db:
            query = db.query(Trade).filter(
                Trade.timestamp >= self.start_date,
                Trade.timestamp <= self.end_date,
            )
            
            if wallet_addresses:
                query = query.filter(Trade.source_wallet.in_(wallet_addresses))
                
            trades = query.order_by(Trade.timestamp.asc()).all()
            
        if not trades:
            logger.warning("[BACKTEST] No historical trades found for period")
            return result
            
        logger.info(f"[BACKTEST] Analyzing {len(trades)} historical trades")
        
        # Simulate trades with current strategy
        portfolio_values = [self.initial_capital]
        daily_returns = []
        
        for trade in trades:
            # Calculate position size using current Kelly
            sizer = PositionSizer()
            sizer.available_capital = self.current_capital
            
            size = sizer.calculate(
                yes_price=float(trade.price),
                conviction_score=0.75,  # Default mid-range
                source_amount=float(trade.source_amount or 100),
            )
            
            # Simulate trade outcome
            if trade.pnl_usdc:
                # Use actual PnL if available
                pnl = float(trade.pnl_usdc)
            else:
                # Estimate based on TP/SL rules
                pnl = self._estimate_pnl(trade, size.amount_usdc)
                
            self.current_capital += pnl
            portfolio_values.append(self.current_capital)
            
            # Track metrics
            result.total_trades += 1
            result.total_pnl += pnl
            
            if pnl > 0:
                result.winning_trades += 1
                daily_returns.append(pnl / self.current_capital)
            else:
                result.losing_trades += 1
                
            # Update peak for drawdown calculation
            if self.current_capital > self.peak_capital:
                self.peak_capital = self.current_capital
                
        # Calculate final metrics
        result.total_return_pct = (
            (self.current_capital - self.initial_capital) / self.initial_capital
        )
        result.win_rate = (
            result.winning_trades / result.total_trades if result.total_trades > 0 else 0
        )
        
        # Sharpe ratio (annualized)
        if daily_returns:
            returns_series = pd.Series(daily_returns)
            result.sharpe_ratio = (
                returns_series.mean() / returns_series.std() * (252 ** 0.5)
                if returns_series.std() > 0 else 0
            )
            
        # Max drawdown
        portfolio_series = pd.Series(portfolio_values)
        peak_series = portfolio_series.expanding().max()
        drawdown_series = (portfolio_series - peak_series) / peak_series
        result.max_drawdown = drawdown_series.min() * self.initial_capital
        result.max_drawdown_pct = drawdown_series.min()
        
        # Average win/loss
        wins = [t.pnl_usdc for t in trades if t.pnl_usdc and t.pnl_usdc > 0]
        losses = [t.pnl_usdc for t in trades if t.pnl_usdc and t.pnl_usdc < 0]
        
        result.avg_win = sum(wins) / len(wins) if wins else 0
        result.avg_loss = abs(sum(losses) / len(losses)) if losses else 0
        
        # Profit factor
        total_wins = sum(wins) if wins else 0
        total_losses = abs(sum(losses)) if losses else 1
        result.profit_factor = total_wins / total_losses if total_losses > 0 else 0
        
        # Trades per day
        days = (self.end_date - self.start_date).days + 1
        result.trades_per_day = result.total_trades / days if days > 0 else 0
        
        logger.info(
            f"[BACKTEST] Completed: WR={result.win_rate:.1%} | "
            f"Return={result.total_return_pct:.1%} | Sharpe={result.sharpe_ratio:.2f}"
        )
        
        return result
        
    def _estimate_pnl(self, trade: Trade, position_size: float) -> float:
        """Estimate PnL if not recorded (using TP/SL rules)"""
        # Simplified: 70% hit TP1 (+20%), 20% hit SL (-30%), 10% neutral
        import random
        rand = random.random()
        
        if rand < 0.70:
            return position_size * 0.20  # TP1
        elif rand < 0.90:
            return position_size * -0.30  # SL
        else:
            return 0  # Neutral
