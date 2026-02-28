"""
Backtest Engine v1.0
=====================
Replay trades historiques avec stratégie actuelle (Kelly, TP/SL, filtres).
Calcule Sharpe ratio, max drawdown, win rate par période.

Usage:
    python -m bot.analytics.backtest --start 2025-01-01 --end 2026-02-28
"""
import asyncio
from datetime import datetime, timedelta
from typing import List, Dict, Optional
from dataclasses import dataclass
import statistics

from sqlalchemy import text

from bot.database import get_db, CopiedTrade, TrackedWallet
from bot.trading.risk import RiskManager
from bot.trading.sizing import PositionSizer
from bot.trading.filters import ConvictionFilter
from bot.config import get_settings
from bot.utils.logger import logger

settings = get_settings()


@dataclass
class BacktestResult:
    """Résultat d'un backtest."""
    total_trades: int
    winning_trades: int
    losing_trades: int
    win_rate: float
    total_pnl_usdc: float
    total_return_pct: float
    max_drawdown_pct: float
    sharpe_ratio: float
    avg_trade_duration_hours: float
    avg_win_usdc: float
    avg_loss_usdc: float
    start_date: str
    end_date: str
    final_capital: float
    peak_capital: float
    
    def to_dict(self) -> dict:
        return {
            "total_trades": self.total_trades,
            "winning_trades": self.winning_trades,
            "losing_trades": self.losing_trades,
            "win_rate": round(self.win_rate, 4),
            "total_pnl_usdc": round(self.total_pnl_usdc, 2),
            "total_return_pct": round(self.total_return_pct, 4),
            "max_drawdown_pct": round(self.max_drawdown_pct, 4),
            "sharpe_ratio": round(self.sharpe_ratio, 2),
            "avg_trade_duration_hours": round(self.avg_trade_duration_hours, 1),
            "avg_win_usdc": round(self.avg_win_usdc, 2),
            "avg_loss_usdc": round(self.avg_loss_usdc, 2),
            "start_date": self.start_date,
            "end_date": self.end_date,
            "final_capital": round(self.final_capital, 2),
            "peak_capital": round(self.peak_capital, 2),
        }


class BacktestEngine:
    """
    Moteur de backtesting avec replay historique.
    Simule les décisions de trading avec les paramètres actuels.
    """
    
    def __init__(
        self,
        initial_capital: float = 500.0,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
    ):
        self.initial_capital = initial_capital
        self.start_date = start_date or (datetime.utcnow() - timedelta(days=30)).strftime("%Y-%m-%d")
        self.end_date = end_date or datetime.utcnow().strftime("%Y-%m-%d")
        
        # Composants stratégie
        self.risk_manager = RiskManager()
        self.sizer = PositionSizer()
        self.conv_filter = ConvictionFilter()
        
        # Tracking backtest
        self.capital = initial_capital
        self.peak_capital = initial_capital
        self.trades_history: List[Dict] = []
        self.equity_curve: List[float] = [initial_capital]
        
    async def run(self) -> BacktestResult:
        """
        Lance le backtest complet sur la période définie.
        Rejoue chaque trade historique avec les filtres actuels.
        """
        logger.info(f"[BACKTEST] Starting from {self.start_date} to {self.end_date}")
        logger.info(f"[BACKTEST] Initial capital: ${self.initial_capital}")
        
        # Récupère tous les trades historiques de la période
        with get_db() as db:
            trades = db.query(CopiedTrade).filter(
                CopiedTrade.created_at >= datetime.fromisoformat(self.start_date),
                CopiedTrade.created_at <= datetime.fromisoformat(self.end_date),
                CopiedTrade.status == "executed",
            ).order_by(CopiedTrade.created_at).all()
            
            # Charge les wallets pour scoring
            wallet_scores = {}
            for wallet in db.query(TrackedWallet).all():
                wallet_scores[wallet.address] = float(wallet.score or 0.70)
        
        if not trades:
            logger.warning(f"[BACKTEST] No trades found between {self.start_date} and {self.end_date}")
            return self._generate_empty_result()
        
        logger.info(f"[BACKTEST] Found {len(trades)} historical trades to replay")
        
        # Replay chaque trade
        for trade in trades:
            await self._replay_trade(trade, wallet_scores.get(trade.source_wallet_address, 0.70))
        
        # Calcul métriques finales
        result = self._calculate_metrics()
        logger.info(f"[BACKTEST] Completed — Win Rate: {result.win_rate:.1%} | PnL: ${result.total_pnl_usdc:+.2f} | Sharpe: {result.sharpe_ratio:.2f}")
        return result
    
    async def _replay_trade(self, trade: CopiedTrade, wallet_score: float) -> None:
        """
        Rejoue un trade historique avec les filtres actuels.
        Simule l'exécution et le PnL.
        """
        # Applique filtres conviction
        filter_result = self.conv_filter.evaluate(
            source_amount=trade.amount_usdc,
            price=trade.price,
            wallet_score=wallet_score,
            market_id=trade.market_id or "",
            consecutive_losses=0,  # Pas de data historique
            entry_timing_score=0.5,
        )
        
        if not filter_result.passed:
            return
        
        # Applique risk management
        decision = self.risk_manager.evaluate(
            token_id=trade.token_id,
            price=trade.price,
            source_amount=trade.amount_usdc,
            wallet_win_rate=wallet_score,
            is_convergence_signal=False,
        )
        
        if not decision.approved:
            return
        
        # Calcule sizing avec Kelly
        self.sizer.sync_capital(self.risk_manager)
        size = self.sizer.calculate(
            yes_price=trade.price,
            conviction_score=filter_result.score,
            source_amount=trade.amount_usdc,
        )
        
        # Simule PnL (assume TP1 +20% si win, SL -30% si loss)
        # Dans la vraie vie, tu pourrais fetcher les prix réels de résolution
        simulated_pnl = trade.pnl_usdc if trade.pnl_usdc else 0.0
        
        # Si pas de PnL historique, simule basé sur wallet score
        if simulated_pnl == 0.0:
            import random
            if random.random() < wallet_score:
                # Win: TP1 à +20%
                simulated_pnl = size.amount_usdc * 0.20
            else:
                # Loss: SL à -30%
                simulated_pnl = size.amount_usdc * -0.30
        
        # Update capital
        self.capital += simulated_pnl
        self.peak_capital = max(self.peak_capital, self.capital)
        self.equity_curve.append(self.capital)
        
        # Enregistre trade
        self.trades_history.append({
            "date": trade.created_at,
            "token_id": trade.token_id,
            "side": trade.side,
            "amount_usdc": size.amount_usdc,
            "price": trade.price,
            "pnl_usdc": simulated_pnl,
            "wallet_score": wallet_score,
            "conviction_score": filter_result.score,
        })
    
    def _calculate_metrics(self) -> BacktestResult:
        """Calcule toutes les métriques de performance."""
        if not self.trades_history:
            return self._generate_empty_result()
        
        winning = [t for t in self.trades_history if t["pnl_usdc"] > 0]
        losing = [t for t in self.trades_history if t["pnl_usdc"] < 0]
        
        total_pnl = sum(t["pnl_usdc"] for t in self.trades_history)
        win_rate = len(winning) / len(self.trades_history) if self.trades_history else 0.0
        
        # Max drawdown
        max_dd = 0.0
        peak = self.initial_capital
        for equity in self.equity_curve:
            if equity > peak:
                peak = equity
            dd = (peak - equity) / peak if peak > 0 else 0.0
            max_dd = max(max_dd, dd)
        
        # Sharpe ratio (assume 0% risk-free rate)
        returns = []
        for i in range(1, len(self.equity_curve)):
            ret = (self.equity_curve[i] - self.equity_curve[i-1]) / self.equity_curve[i-1]
            returns.append(ret)
        
        sharpe = 0.0
        if returns and statistics.stdev(returns) > 0:
            avg_return = statistics.mean(returns)
            sharpe = (avg_return / statistics.stdev(returns)) * (252 ** 0.5)  # Annualisé
        
        avg_win = statistics.mean([t["pnl_usdc"] for t in winning]) if winning else 0.0
        avg_loss = statistics.mean([t["pnl_usdc"] for t in losing]) if losing else 0.0
        
        return BacktestResult(
            total_trades=len(self.trades_history),
            winning_trades=len(winning),
            losing_trades=len(losing),
            win_rate=win_rate,
            total_pnl_usdc=total_pnl,
            total_return_pct=(self.capital - self.initial_capital) / self.initial_capital,
            max_drawdown_pct=max_dd,
            sharpe_ratio=sharpe,
            avg_trade_duration_hours=24.0,  # Placeholder — calcul réel nécessite exit timestamps
            avg_win_usdc=avg_win,
            avg_loss_usdc=avg_loss,
            start_date=self.start_date,
            end_date=self.end_date,
            final_capital=self.capital,
            peak_capital=self.peak_capital,
        )
    
    def _generate_empty_result(self) -> BacktestResult:
        """Génère un résultat vide si aucun trade."""
        return BacktestResult(
            total_trades=0,
            winning_trades=0,
            losing_trades=0,
            win_rate=0.0,
            total_pnl_usdc=0.0,
            total_return_pct=0.0,
            max_drawdown_pct=0.0,
            sharpe_ratio=0.0,
            avg_trade_duration_hours=0.0,
            avg_win_usdc=0.0,
            avg_loss_usdc=0.0,
            start_date=self.start_date,
            end_date=self.end_date,
            final_capital=self.initial_capital,
            peak_capital=self.initial_capital,
        )


async def run_backtest(
    start_date: str,
    end_date: str,
    initial_capital: float = 500.0,
) -> BacktestResult:
    """
    Interface publique pour lancer un backtest.
    
    Args:
        start_date: Date début format YYYY-MM-DD
        end_date: Date fin format YYYY-MM-DD
        initial_capital: Capital initial en USDC
    
    Returns:
        BacktestResult avec toutes les métriques
    """
    engine = BacktestEngine(
        initial_capital=initial_capital,
        start_date=start_date,
        end_date=end_date,
    )
    return await engine.run()


if __name__ == "__main__":
    import sys
    
    # Parse args simples
    args = sys.argv[1:]
    start = None
    end = None
    
    for i, arg in enumerate(args):
        if arg == "--start" and i + 1 < len(args):
            start = args[i + 1]
        if arg == "--end" and i + 1 < len(args):
            end = args[i + 1]
    
    if not start:
        start = (datetime.utcnow() - timedelta(days=30)).strftime("%Y-%m-%d")
    if not end:
        end = datetime.utcnow().strftime("%Y-%m-%d")
    
    result = asyncio.run(run_backtest(start, end))
    
    print("\n" + "=" * 60)
    print("  BACKTEST RESULTS")
    print("=" * 60)
    for key, value in result.to_dict().items():
        print(f"{key:.<40} {value}")
    print("=" * 60)
