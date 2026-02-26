"""
PerformanceTracker — PolyInsider Bot

FIX PERF-P0-1: win_rate était toujours 1.0 à cause du 'or True' L.55
  Avant: wins = [t for t in executed if t.skip_reason != 'DRY_RUN' or True]
  Après: wins = trades clôturés avec pnl_usdc > 0

FIX PERF-P0-2: total_pnl_usdc était la somme du capital investi (amount_usdc)
  Avant: total_amount = sum(t.amount_usdc for t in executed) -> montant mis
  Après: total_pnl = sum(t.pnl_usdc for t in closed)         -> profit réel

FIX PERF-P0-3: WalletPerformance.total_profit accumulait amount_usdc (capital)
  Avant: snap.total_profit += trade.amount_usdc
  Après: snap.total_profit += trade.pnl_usdc or 0.0 (profit réel)

FIX #9 — WalletPerformance toujours alimentée à chaque record_trade().
"""
from datetime import datetime
from typing import Any

from bot.database import get_db, CopiedTrade, TradeStatus, WalletPerformance
from bot.utils.logger import logger

# Statuts qui indiquent un trade clôturé (position fermée, PnL connu)
_CLOSED_SKIP_REASONS = ("CLOSED", "TP1", "TP2", "SL", "MAX_HOLD", "RESOLVING")


def _is_closed(trade: CopiedTrade) -> bool:
    """True si le trade a été clôturé (position fermée, PnL disponible)."""
    if not trade.skip_reason:
        return False
    return any(trade.skip_reason.upper().startswith(r) for r in _CLOSED_SKIP_REASONS)


def _is_dry_run(trade: CopiedTrade) -> bool:
    """True si le trade est un DRY_RUN (ne compte pas dans les stats réelles)."""
    return (trade.skip_reason or "").upper() == "DRY_RUN"


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
                    # FIX PERF-P0-3: utilise pnl_usdc (profit réel) et non amount_usdc (capital)
                    # pnl_usdc est mis à jour par ExitManager quand la position se ferme
                    pnl = trade.pnl_usdc if trade.pnl_usdc is not None else 0.0
                    snap.total_profit = (snap.total_profit or 0.0) + pnl
        except Exception as e:
            logger.warning(f"[PERF] record_trade error: {e}")

    async def get_summary(self) -> dict[str, Any]:
        """
        Retourne un résumé agrégé de tous les trades en DB.

        Win rate = trades clôturés avec pnl_usdc > 0 / total trades clôturés
        total_pnl_usdc = somme des pnl_usdc (profit/perte réel, pas le capital investi)
        """
        try:
            with get_db() as db:
                trades = db.query(CopiedTrade).all()

                # Exclut les DRY_RUN des stats réelles
                live_trades = [t for t in trades if not _is_dry_run(t)]
                executed    = [t for t in live_trades if t.status == TradeStatus.EXECUTED]
                total       = len(executed)

                if total == 0:
                    return {
                        "total_trades":   0,
                        "open_trades":    0,
                        "closed_trades":  0,
                        "win_rate":       0.0,
                        "total_pnl_usdc": 0.0,
                    }

                # FIX PERF-P0-1: wins = trades clôturés avec profit réel > 0
                # Avant: or True → tous les trades étaient wins → win_rate = 1.0
                closed = [t for t in executed if _is_closed(t)]
                open_  = [t for t in executed if not _is_closed(t)]
                wins   = [
                    t for t in closed
                    if t.pnl_usdc is not None and t.pnl_usdc > 0
                ]

                # Win rate sur les trades clôturés uniquement (PnL connu)
                win_rate = len(wins) / len(closed) if closed else 0.0

                # FIX PERF-P0-2: PnL réel = somme pnl_usdc, pas somme amount_usdc
                # Avant: total_amount = sum(t.amount_usdc) → capital investi, pas profit
                total_pnl = sum(
                    t.pnl_usdc for t in closed if t.pnl_usdc is not None
                )

                logger.debug(
                    f"[PERF] summary: {total} trades "
                    f"({len(open_)} open, {len(closed)} closed) "
                    f"wins={len(wins)} WR={win_rate:.1%} PnL={total_pnl:+.2f}$"
                )

                return {
                    "total_trades":   total,
                    "open_trades":    len(open_),
                    "closed_trades":  len(closed),
                    "win_rate":       win_rate,
                    "total_pnl_usdc": total_pnl,
                }
        except Exception as e:
            logger.warning(f"[PERF] get_summary error: {e}")
            return {
                "total_trades":   0,
                "open_trades":    0,
                "closed_trades":  0,
                "win_rate":       0.0,
                "total_pnl_usdc": 0.0,
            }
