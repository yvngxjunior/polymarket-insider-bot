"""Features Integration v1.0 - Activate new bot features"""
import asyncio
from typing import Optional
from datetime import datetime

from bot.trading.exit_strategy import ExitStrategy
from bot.scanner.wallet_discovery import WalletDiscovery, WalletDiscoveryConfig
from bot.utils.logger import logger


class FeaturesManager:
    """
    Central manager for bot features.
    Handles:
    - Trailing Stop-Loss
    - Wallet Discovery (periodic)
    """
    
    def __init__(
        self,
        enable_trailing_sl: bool = True,
        enable_wallet_discovery: bool = True,
        discovery_interval_hours: int = 24,
    ):
        self.enable_trailing_sl = enable_trailing_sl
        self.enable_wallet_discovery = enable_wallet_discovery
        self.discovery_interval_hours = discovery_interval_hours
        
        # Exit strategy with trailing SL
        self.exit_strategy = ExitStrategy(use_trailing_sl=enable_trailing_sl)
        
        # Wallet discovery
        self.wallet_discovery: Optional[WalletDiscovery] = None
        if enable_wallet_discovery:
            config = WalletDiscoveryConfig()
            self.wallet_discovery = WalletDiscovery(config)
            
        self._discovery_task: Optional[asyncio.Task] = None
        self._running = False
        
    async def start(self):
        """Start all enabled features"""
        logger.info("[FEATURES] Starting features manager...")
        
        if self.enable_trailing_sl:
            logger.info("✅ [FEATURES] Trailing Stop-Loss: ENABLED")
        else:
            logger.info("❌ [FEATURES] Trailing Stop-Loss: DISABLED")
            
        if self.enable_wallet_discovery:
            logger.info(
                f"✅ [FEATURES] Wallet Discovery: ENABLED "
                f"(every {self.discovery_interval_hours}h)"
            )
            self._running = True
            self._discovery_task = asyncio.create_task(self._discovery_loop())
        else:
            logger.info("❌ [FEATURES] Wallet Discovery: DISABLED")
            
    async def stop(self):
        """Stop all features"""
        logger.info("[FEATURES] Stopping features manager...")
        self._running = False
        
        if self._discovery_task:
            self._discovery_task.cancel()
            try:
                await self._discovery_task
            except asyncio.CancelledError:
                pass
                
        if self.wallet_discovery:
            await self.wallet_discovery.close()
            
    async def _discovery_loop(self):
        """Periodic wallet discovery task"""
        # Run first discovery immediately
        await self._run_discovery()
        
        # Then run every N hours
        while self._running:
            try:
                await asyncio.sleep(self.discovery_interval_hours * 3600)
                await self._run_discovery()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"[FEATURES] Discovery loop error: {e}")
                await asyncio.sleep(60)  # Wait 1min before retry
                
    async def _run_discovery(self):
        """Run single discovery cycle"""
        if not self.wallet_discovery:
            return
            
        try:
            logger.info("[FEATURES] Running wallet discovery...")
            stats = await self.wallet_discovery.run_discovery()
            
            logger.info(
                f"✅ [FEATURES] Discovery complete | "
                f"Fetched: {stats['fetched']} | "
                f"Qualified: {stats['qualified']} | "
                f"Added: {stats['added']}"
            )
            
        except Exception as e:
            logger.error(f"[FEATURES] Discovery failed: {e}")
            
    def check_position_exit(
        self,
        position_id: str,
        entry_price: float,
        current_price: float,
        entry_time: datetime,
    ) -> tuple[bool, str, Optional[float]]:
        """Check if position should exit (delegates to ExitStrategy)"""
        return self.exit_strategy.check_exit(
            position_id,
            entry_price,
            current_price,
            entry_time,
        )
        
    def register_new_position(
        self,
        position_id: str,
        entry_price: float,
    ):
        """Register new position for tracking"""
        self.exit_strategy.register_position(position_id, entry_price)
        
    def on_position_closed(self, position_id: str):
        """Clean up after position closes"""
        self.exit_strategy.on_position_closed(position_id)


# Global instance (can be imported in main.py)
_features_manager: Optional[FeaturesManager] = None


def get_features_manager(
    enable_trailing_sl: bool = True,
    enable_wallet_discovery: bool = True,
) -> FeaturesManager:
    """Get or create global features manager"""
    global _features_manager
    if _features_manager is None:
        _features_manager = FeaturesManager(
            enable_trailing_sl=enable_trailing_sl,
            enable_wallet_discovery=enable_wallet_discovery,
        )
    return _features_manager
