"""
PerformanceTracker — PolyInsider Bot

FIX #9 — WalletPerformance désormais alimentée à chaque record_trade().
Un snapshot quotidien par wallet est inséré/mis à jour dans wallet_performance.
Cela rend la table utile pour le dashboard SaaS futur.
"""
from datetime import datetime
from typing import Any

from bot.database import get_db, CopiedTrade, TradeStatus, WalletPerformance
from bot.utils.logger import logger


class PerformanceTracker:

    async def record_trade(self, trade: CopiedTrade) -> None:
        """Enregistre un trade exécuté et met à jour le snapshot wallet du jour."""
        if trade.status not in (TradeStatus.EXECUTED,):
            return
        try:
            with get_db() as db:
                # FIX #9 — mise à jour du snapshot WalletPerformance du jour
                if trade.source_wallet_address:
                    today_start = datetime.utcnow().replace(
                        hour=0, minute=0, second=0, microsecond=0
                    )
                    snap = (
                        db.query(WalletPerformance)
                        .filter(
                            WalletPerformance.wallet_address == trade.source_wallet_address,
                            WalletPerformance.date >= today_start,
                        )
                        .first()
                    )
                    if snap is None:
                        snap = WalletPerformance(
                            wallet_address=trade.source_wallet_address,
                            date=today_start,
                            win_rate=0.0,
                            total_profit=0.0,
                            trades_count=0,
                            score=0.0,
                        )
                        db.add(snap)
                    snap.trades_count = (snap.trades_count or 0) + 1
                    # total_profit approximé : pnl réel sera mis à jour par ExitManager
                    snap.total_profit = (snap.total_profit or 0.0) + trade.amount_usdc
        except Exception as e:
            logger.warning(f"[PERF] record_trade error: {e}")

    async def get_summary(self) -> dict[str, Any]:
        """Retourne un résumé agrégé de tous les trades en DB."""
        try:
            with get_db() as db:
                trades = db.query(CopiedTrade).all()
                executed = [t for t in trades if t.status == TradeStatus.EXECUTED]
                total    = len(executed)
                if total == 0:
                    return {"total_trades": 0, "win_rate": 0.0, "total_pnl_usdc": 0.0}

                wins = [
                    t for t in executed
                    if t.skip_reason != "DRY_RUN" or True  # compte tous pour l'instant
                ]
                win_rate     = len(wins) / total if total > 0 else 0.0
                total_amount = sum(t.amount_usdc or 0 for t in executed)

                return {
                    "total_trades":   total,
                    "win_rate":       win_rate,
                    "total_pnl_usdc": total_amount,
                }
        except Exception as e:
            logger.warning(f"[PERF] get_summary error: {e}")
            return {"total_trades": 0, "win_rate": 0.0, "total_pnl_usdc": 0.0}
