from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy import func

from bot.database import get_db, CopiedTrade, TradeStatus
from bot.notifications.telegram import TelegramNotifier
from bot.trading.risk import RiskManager
from bot.utils.logger import logger


class PerformanceTracker:
    """
    Calcule les métriques de performance et envoie des rapports périodiques.

    Métriques trackées:
      - P&L total et journalier
      - Taux de réussite des copies
      - Meilleur et pire trade
      - Ratio Sharpe simplifié
      - Capital évolution
    """

    def __init__(self, notifier: TelegramNotifier, risk: RiskManager):
        self.notifier = notifier
        self.risk = risk

    async def send_daily_report(self) -> None:
        """Génère et envoie le rapport quotidien."""
        since = datetime.utcnow() - timedelta(days=1)
        stats = self._compute_stats(since)

        capital = self.risk.portfolio.total_capital
        drawdown = self.risk.portfolio.drawdown_pct
        open_pos = len(self.risk._open_positions)

        emoji_pnl = "📈" if stats["total_pnl"] >= 0 else "📉"

        msg = (
            f"{emoji_pnl} <b>Daily Report</b> — {datetime.utcnow().strftime('%d/%m/%Y')}
"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"💰 P&L (24h): <b>${stats['total_pnl']:+.2f}</b>\n"
            f"🏦 Capital: <b>${capital:.2f}</b>\n"
            f"📉 Drawdown: <b>{drawdown:.1%}</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"✅ Trades exécutés: <b>{stats['executed']}</b>\n"
            f"⛔ Trades skippés: <b>{stats['skipped']}</b>\n"
            f"❌ Trades failed: <b>{stats['failed']}</b>\n"
            f"🎯 Success rate: <b>{stats['success_rate']:.0%}</b>\n"
            f"📊 Open positions: <b>{open_pos}</b>\n"
            + (
                f"━━━━━━━━━━━━━━━━━━━━\n"
                f"🏆 Best: {stats['best_trade']}\n"
                f"💀 Worst: {stats['worst_trade']}\n"
                if stats['best_trade'] else ""
            )
        )
        await self.notifier.send(msg)
        logger.info(f"Daily report sent. P&L: ${stats['total_pnl']:+.2f}")

    async def send_weekly_report(self) -> None:
        """Rapport hebdomadaire avec Sharpe ratio."""
        since = datetime.utcnow() - timedelta(days=7)
        stats = self._compute_stats(since)
        stats_daily = [self._compute_stats(
            datetime.utcnow() - timedelta(days=i+1),
            datetime.utcnow() - timedelta(days=i)
        ) for i in range(7)]

        daily_pnls = [s["total_pnl"] for s in stats_daily]
        sharpe = self._sharpe_ratio(daily_pnls)

        msg = (
            f"📊 <b>Weekly Report</b> — {datetime.utcnow().strftime('W%V %Y')}
"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"💰 P&L (7j): <b>${stats['total_pnl']:+.2f}</b>\n"
            f"📈 Sharpe Ratio: <b>{sharpe:.2f}</b>\n"
            f"🎯 Success rate: <b>{stats['success_rate']:.0%}</b>\n"
            f"🔄 Total trades: <b>{stats['executed']}</b>\n"
        )
        await self.notifier.send(msg)

    def _compute_stats(
        self,
        since: datetime,
        until: Optional[datetime] = None
    ) -> dict:
        """Calcule les stats sur une période donnée."""
        until = until or datetime.utcnow()
        try:
            with get_db() as db:
                trades = (
                    db.query(CopiedTrade)
                    .filter(
                        CopiedTrade.created_at >= since,
                        CopiedTrade.created_at <= until,
                    )
                    .all()
                )

            executed = [t for t in trades if t.status == TradeStatus.EXECUTED and t.skip_reason != "DRY_RUN"]
            skipped = [t for t in trades if t.status == TradeStatus.SKIPPED]
            failed = [t for t in trades if t.status == TradeStatus.FAILED]

            # Calcul P&L simplifié (estimation basée sur les montants)
            total_invested = sum(t.amount_usdc for t in executed)
            total_pnl = self.risk.portfolio.daily_pnl  # du risk manager

            success_rate = len(executed) / len(trades) if trades else 0

            # Best/worst trade par montant
            best = max(executed, key=lambda t: t.amount_usdc, default=None)
            worst = min(executed, key=lambda t: t.amount_usdc, default=None)

            return {
                "total_pnl": total_pnl,
                "executed": len(executed),
                "skipped": len(skipped),
                "failed": len(failed),
                "success_rate": success_rate,
                "best_trade": f"{best.market_question[:30]}... ${best.amount_usdc:.0f}" if best else None,
                "worst_trade": f"{worst.market_question[:30]}... ${worst.amount_usdc:.0f}" if worst else None,
            }
        except Exception as e:
            logger.error(f"Stats computation error: {e}")
            return {"total_pnl": 0, "executed": 0, "skipped": 0, "failed": 0, "success_rate": 0, "best_trade": None, "worst_trade": None}

    @staticmethod
    def _sharpe_ratio(daily_pnls: list[float], risk_free_rate: float = 0.0) -> float:
        """Sharpe ratio simplifié sur une liste de P&L journaliers."""
        if len(daily_pnls) < 2:
            return 0.0
        import statistics
        avg = statistics.mean(daily_pnls) - risk_free_rate
        std = statistics.stdev(daily_pnls)
        return avg / std if std > 0 else 0.0
