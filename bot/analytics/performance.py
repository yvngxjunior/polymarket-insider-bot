from datetime import datetime, timedelta
from typing import Optional

from bot.database import get_db, CopiedTrade, TradeStatus
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

    Méthodes:
      - record_trade(trade)  → enregistre un trade exécuté
      - get_summary()        → retourne dict win_rate / total_pnl_usdc / total_trades
      - send_daily_report()  → envoie le rapport via Telegram
      - send_weekly_report() → rapport hebdomadaire avec Sharpe ratio
    """

    def __init__(self, notifier=None, risk=None) -> None:
        # notifier et risk sont optionnels — requis seulement pour les rapports Telegram
        self.notifier = notifier
        self.risk = risk
        self._trade_log: list[dict] = []   # cache mémoire léger

    # ------------------------------------------------------------------
    # Interface principale (appelée depuis main.py)
    # ------------------------------------------------------------------

    async def record_trade(self, trade: CopiedTrade) -> None:
        """Enregistre un trade exécuté dans le cache mémoire."""
        try:
            self._trade_log.append(
                {
                    "token_id": trade.token_id,
                    "side": trade.side,
                    "amount_usdc": trade.amount_usdc,
                    "price": trade.price,
                    "status": trade.status,
                    "recorded_at": datetime.utcnow(),
                }
            )
        except Exception as e:
            logger.debug(f"[PERF] record_trade error: {e}")

    async def get_summary(self) -> dict:
        """
        Retourne un résumé des métriques depuis le démarrage.

        Returns:
            dict avec clés: win_rate, total_pnl_usdc, total_trades, executed, skipped
        """
        try:
            stats = self._compute_stats(since=datetime(2020, 1, 1))
            return {
                "win_rate": stats["success_rate"],
                "total_pnl_usdc": stats["total_pnl"],
                "total_trades": stats["executed"] + stats["skipped"] + stats["failed"],
                "executed": stats["executed"],
                "skipped": stats["skipped"],
                "failed": stats["failed"],
            }
        except Exception as e:
            logger.debug(f"[PERF] get_summary error: {e}")
            return {
                "win_rate": 0.0,
                "total_pnl_usdc": 0.0,
                "total_trades": 0,
                "executed": 0,
                "skipped": 0,
                "failed": 0,
            }

    # ------------------------------------------------------------------
    # Rapports Telegram (optionnels — notifier requis)
    # ------------------------------------------------------------------

    async def send_daily_report(self) -> None:
        """Génère et envoie le rapport quotidien via Telegram."""
        if not self.notifier:
            logger.warning("[PERF] send_daily_report: no notifier configured")
            return

        since = datetime.utcnow() - timedelta(days=1)
        stats = self._compute_stats(since)

        capital_info = ""
        if self.risk:
            capital = self.risk.portfolio.total_capital
            drawdown = self.risk.portfolio.drawdown_pct
            open_pos = len(self.risk._open_positions)
            capital_info = (
                f"🏦 Capital: <b>${capital:.2f}</b>\n"
                f"📉 Drawdown: <b>{drawdown:.1%}</b>\n"
                f"📊 Open positions: <b>{open_pos}</b>\n"
            )

        emoji_pnl = "📈" if stats["total_pnl"] >= 0 else "📉"
        msg = (
            f"{emoji_pnl} <b>Daily Report</b> — "
            f"{datetime.utcnow().strftime('%d/%m/%Y')}\n"
            f"────────────────────\n"
            f"💰 P&L (24h): <b>${stats['total_pnl']:+.2f}</b>\n"
            + capital_info
            + f"────────────────────\n"
            f"✅ Exécutés: <b>{stats['executed']}</b>\n"
            f"⛔ Skippés: <b>{stats['skipped']}</b>\n"
            f"❌ Failed: <b>{stats['failed']}</b>\n"
            f"🎯 Success rate: <b>{stats['success_rate']:.0%}</b>\n"
            + (
                f"────────────────────\n"
                f"🏆 Best: {stats['best_trade']}\n"
                f"💧 Worst: {stats['worst_trade']}\n"
                if stats["best_trade"]
                else ""
            )
        )
        await self.notifier.send(msg)
        logger.info(f"[PERF] Daily report sent. P&L: ${stats['total_pnl']:+.2f}")

    async def send_weekly_report(self) -> None:
        """Rapport hebdomadaire avec Sharpe ratio."""
        if not self.notifier:
            return

        since = datetime.utcnow() - timedelta(days=7)
        stats = self._compute_stats(since)

        stats_daily = [
            self._compute_stats(
                datetime.utcnow() - timedelta(days=i + 1),
                datetime.utcnow() - timedelta(days=i),
            )
            for i in range(7)
        ]
        daily_pnls = [s["total_pnl"] for s in stats_daily]
        sharpe = self._sharpe_ratio(daily_pnls)

        msg = (
            f"📊 <b>Weekly Report</b> — "
            f"{datetime.utcnow().strftime('W%V %Y')}\n"
            f"────────────────────\n"
            f"💰 P&L (7j): <b>${stats['total_pnl']:+.2f}</b>\n"
            f"📈 Sharpe Ratio: <b>{sharpe:.2f}</b>\n"
            f"🎯 Success rate: <b>{stats['success_rate']:.0%}</b>\n"
            f"🔄 Total trades: <b>{stats['executed']}</b>\n"
        )
        await self.notifier.send(msg)

    # ------------------------------------------------------------------
    # Helpers internes
    # ------------------------------------------------------------------

    def _compute_stats(
        self,
        since: datetime,
        until: Optional[datetime] = None,
    ) -> dict:
        """Calcule les stats sur une période donnée depuis la DB."""
        until = until or datetime.utcnow()
        empty = {
            "total_pnl": 0.0,
            "executed": 0,
            "skipped": 0,
            "failed": 0,
            "success_rate": 0.0,
            "best_trade": None,
            "worst_trade": None,
        }
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

            if not trades:
                return empty

            executed = [
                t for t in trades
                if t.status == TradeStatus.EXECUTED
                and t.skip_reason != "DRY_RUN"
            ]
            skipped = [t for t in trades if t.status == TradeStatus.SKIPPED]
            failed  = [t for t in trades if t.status == TradeStatus.FAILED]

            total_pnl = self.risk.portfolio.daily_pnl if self.risk else 0.0
            success_rate = len(executed) / len(trades) if trades else 0.0

            best  = max(executed, key=lambda t: t.amount_usdc, default=None)
            worst = min(executed, key=lambda t: t.amount_usdc, default=None)

            return {
                "total_pnl": total_pnl,
                "executed": len(executed),
                "skipped": len(skipped),
                "failed": len(failed),
                "success_rate": success_rate,
                "best_trade": (
                    f"{best.market_question[:30]}... ${best.amount_usdc:.0f}"
                    if best else None
                ),
                "worst_trade": (
                    f"{worst.market_question[:30]}... ${worst.amount_usdc:.0f}"
                    if worst else None
                ),
            }

        except Exception as e:
            logger.error(f"[PERF] Stats computation error: {e}")
            return empty

    @staticmethod
    def _sharpe_ratio(
        daily_pnls: list[float],
        risk_free_rate: float = 0.0,
    ) -> float:
        """Sharpe ratio simplifié sur une liste de P&L journaliers."""
        if len(daily_pnls) < 2:
            return 0.0
        import statistics
        avg = statistics.mean(daily_pnls) - risk_free_rate
        std = statistics.stdev(daily_pnls)
        return avg / std if std > 0 else 0.0
