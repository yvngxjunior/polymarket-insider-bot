"""Dynamic Wallet Scoring - Auto recalculate win rates and exclude underperformers"""
import asyncio
from datetime import datetime, timedelta
from typing import List, Optional

from bot.config import get_settings
from bot.database import get_db, TrackedWallet, Trade
from bot.notifications.telegram import TelegramNotifier
from bot.utils.logger import logger

settings = get_settings()


class WalletScorer:
    """Dynamic wallet scoring with periodic recalculation"""
    
    def __init__(
        self,
        notifier: Optional[TelegramNotifier] = None,
        min_trades: int = 10,
        min_win_rate: float = 0.65,
        lookback_days: int = 30,
    ):
        self.notifier = notifier
        self.min_trades = min_trades
        self.min_win_rate = min_win_rate
        self.lookback_days = lookback_days
        self._running = False
        self._task: Optional[asyncio.Task] = None
        
    async def start(self, interval_hours: int = 24):
        """Start periodic scoring task"""
        self._running = True
        self._task = asyncio.create_task(self._scoring_loop(interval_hours))
        logger.info(f"[SCORER] Started (recalc every {interval_hours}h)")
        
    async def stop(self):
        """Stop scoring task"""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("[SCORER] Stopped")
        
    async def _scoring_loop(self, interval_hours: int):
        """Main scoring loop"""
        while self._running:
            try:
                await self.recalculate_all_scores()
            except Exception as e:
                logger.error(f"[SCORER] Error in loop: {e}")
                
            await asyncio.sleep(interval_hours * 3600)
            
    async def recalculate_all_scores(self):
        """Recalculate scores for all tracked wallets"""
        logger.info("[SCORER] Recalculating wallet scores...")
        
        with get_db() as db:
            wallets = (
                db.query(TrackedWallet)
                .filter(TrackedWallet.is_active == True)  # noqa: E712
                .all()
            )
            
        updated_count = 0
        excluded_count = 0
        
        for wallet in wallets:
            try:
                new_score, should_exclude = await self._calculate_wallet_score(
                    wallet.address
                )
                
                if should_exclude:
                    with get_db() as db:
                        db_wallet = (
                            db.query(TrackedWallet)
                            .filter(TrackedWallet.address == wallet.address)
                            .first()
                        )
                        if db_wallet:
                            db_wallet.is_active = False
                            db_wallet.exclusion_reason = (
                                f"Win rate {new_score:.1%} below {self.min_win_rate:.0%}"
                            )
                            db.commit()
                            
                    excluded_count += 1
                    logger.warning(
                        f"[SCORER] Excluded {wallet.address[:10]}... (WR={new_score:.1%})"
                    )
                    
                    if self.notifier:
                        await self.notifier.send(
                            f"⚠️ <b>Wallet Auto-Excluded</b>\n"
                            f"Address: <code>{wallet.address[:10]}...</code>\n"
                            f"Win Rate: {new_score:.1%} (threshold: {self.min_win_rate:.0%})"
                        )
                        
                elif abs(new_score - float(wallet.score or 0)) > 0.05:
                    # Update score if changed significantly
                    with get_db() as db:
                        db_wallet = (
                            db.query(TrackedWallet)
                            .filter(TrackedWallet.address == wallet.address)
                            .first()
                        )
                        if db_wallet:
                            db_wallet.score = new_score
                            db.commit()
                            
                    updated_count += 1
                    logger.info(
                        f"[SCORER] Updated {wallet.address[:10]}... "
                        f"{float(wallet.score or 0):.1%} → {new_score:.1%}"
                    )
                    
            except Exception as e:
                logger.error(f"[SCORER] Error scoring {wallet.address[:10]}: {e}")
                
        logger.info(
            f"[SCORER] Recalc done: {updated_count} updated, {excluded_count} excluded"
        )
        
    async def _calculate_wallet_score(
        self, wallet_address: str
    ) -> tuple[float, bool]:
        """Calculate new score for wallet
        
        Returns:
            (score, should_exclude): New win rate and exclusion flag
        """
        cutoff_date = datetime.utcnow() - timedelta(days=self.lookback_days)
        
        with get_db() as db:
            # Get recent trades from this wallet
            trades = (
                db.query(Trade)
                .filter(
                    Trade.source_wallet == wallet_address,
                    Trade.timestamp >= cutoff_date,
                    Trade.pnl_usdc.isnot(None),
                )
                .all()
            )
            
        if len(trades) < self.min_trades:
            # Not enough data - keep current score
            with get_db() as db:
                wallet = (
                    db.query(TrackedWallet)
                    .filter(TrackedWallet.address == wallet_address)
                    .first()
                )
                return float(wallet.score or 0.70), False
                
        # Calculate win rate
        winning_trades = sum(1 for t in trades if float(t.pnl_usdc) > 0)
        win_rate = winning_trades / len(trades)
        
        # Decide if should exclude
        should_exclude = win_rate < self.min_win_rate
        
        return win_rate, should_exclude
        
    async def force_recalc_wallet(self, wallet_address: str) -> dict:
        """Force recalculation for single wallet (for API/Telegram)"""
        new_score, should_exclude = await self._calculate_wallet_score(wallet_address)
        
        with get_db() as db:
            wallet = (
                db.query(TrackedWallet)
                .filter(TrackedWallet.address == wallet_address)
                .first()
            )
            
            if not wallet:
                return {
                    "error": "Wallet not found",
                    "address": wallet_address,
                }
                
            old_score = float(wallet.score or 0)
            wallet.score = new_score
            
            if should_exclude:
                wallet.is_active = False
                wallet.exclusion_reason = f"Manual recalc: WR {new_score:.1%}"
                
            db.commit()
            
        return {
            "address": wallet_address,
            "old_score": round(old_score, 3),
            "new_score": round(new_score, 3),
            "excluded": should_exclude,
        }
