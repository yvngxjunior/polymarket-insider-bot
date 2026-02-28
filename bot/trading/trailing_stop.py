"""Trailing Stop-Loss v1.0 - Dynamic SL that follows price movements"""
from dataclasses import dataclass
from typing import Dict, Optional
from datetime import datetime

from bot.utils.logger import logger


@dataclass
class TrailingStopConfig:
    """Configuration for trailing stop-loss"""
    
    # Activation thresholds
    activation_gain_pct: float = 0.15  # Active trailing after +15% gain
    
    # Trailing distances (from peak)
    trail_distance_pct: float = 0.05  # Keep SL 5% below peak
    
    # Minimum locked profit
    min_locked_profit_pct: float = 0.10  # Lock at least +10% when trailing
    
    # Initial stop-loss (before trailing activates)
    initial_sl_pct: float = -0.30  # -30% fixed SL initially


class TrailingStopManager:
    """Manages trailing stop-loss for open positions"""
    
    def __init__(self, config: Optional[TrailingStopConfig] = None):
        self.config = config or TrailingStopConfig()
        
        # Track peak price per position
        # Format: {position_id: {"peak_price": float, "entry_price": float}}
        self._peaks: Dict[str, Dict[str, float]] = {}
        
    def register_position(
        self,
        position_id: str,
        entry_price: float,
    ) -> None:
        """Register a new position for trailing SL tracking"""
        self._peaks[position_id] = {
            "peak_price": entry_price,
            "entry_price": entry_price,
            "activated_at": None,
        }
        logger.debug(
            f"[TRAILING_SL] Registered position {position_id} @ {entry_price:.4f}"
        )
        
    def update_peak(
        self,
        position_id: str,
        current_price: float,
    ) -> None:
        """Update peak price if current price is higher"""
        if position_id not in self._peaks:
            logger.warning(
                f"[TRAILING_SL] Position {position_id} not registered, skipping update"
            )
            return
            
        if current_price > self._peaks[position_id]["peak_price"]:
            old_peak = self._peaks[position_id]["peak_price"]
            self._peaks[position_id]["peak_price"] = current_price
            
            logger.debug(
                f"[TRAILING_SL] {position_id} new peak: "
                f"{old_peak:.4f} → {current_price:.4f}"
            )
            
    def calculate_stop_loss(
        self,
        position_id: str,
        current_price: float,
    ) -> float:
        """
        Calculate current stop-loss price.
        
        Logic:
        1. If gain < activation_gain_pct: Use fixed initial_sl_pct
        2. If gain >= activation_gain_pct: Use trailing SL from peak
        3. SL never goes down (ratchet effect)
        
        Returns:
            Stop-loss price (absolute price, not percentage)
        """
        if position_id not in self._peaks:
            # Fallback: use initial SL
            entry_price = current_price  # Assume current as entry
            return entry_price * (1 + self.config.initial_sl_pct)
            
        entry_price = self._peaks[position_id]["entry_price"]
        peak_price = self._peaks[position_id]["peak_price"]
        
        # Update peak if current is higher
        self.update_peak(position_id, current_price)
        peak_price = self._peaks[position_id]["peak_price"]
        
        # Calculate current gain from entry
        current_gain_pct = (current_price - entry_price) / entry_price
        
        # Check if trailing should activate
        if current_gain_pct < self.config.activation_gain_pct:
            # Not profitable enough yet → use fixed initial SL
            sl_price = entry_price * (1 + self.config.initial_sl_pct)
            logger.debug(
                f"[TRAILING_SL] {position_id} using fixed SL: "
                f"{sl_price:.4f} (gain={current_gain_pct:.1%} < "
                f"{self.config.activation_gain_pct:.0%})"
            )
            return sl_price
            
        # Trailing is active → calculate SL from peak
        trailing_sl_price = peak_price * (1 - self.config.trail_distance_pct)
        
        # Ensure minimum locked profit
        min_locked_price = entry_price * (1 + self.config.min_locked_profit_pct)
        final_sl_price = max(trailing_sl_price, min_locked_price)
        
        # Log activation on first time
        if self._peaks[position_id]["activated_at"] is None:
            self._peaks[position_id]["activated_at"] = datetime.utcnow()
            logger.info(
                f"✅ [TRAILING_SL] ACTIVATED for {position_id} @ "
                f"{current_gain_pct:.1%} gain | SL: {final_sl_price:.4f}"
            )
        
        return final_sl_price
        
    def should_exit(
        self,
        position_id: str,
        current_price: float,
    ) -> tuple[bool, str]:
        """
        Check if position should exit based on trailing SL.
        
        Returns:
            (should_exit, reason)
        """
        sl_price = self.calculate_stop_loss(position_id, current_price)
        
        if current_price <= sl_price:
            entry_price = self._peaks[position_id]["entry_price"]
            gain_pct = (current_price - entry_price) / entry_price
            
            reason = (
                f"Trailing SL hit @ {current_price:.4f} "
                f"(SL={sl_price:.4f}, gain={gain_pct:+.1%})"
            )
            logger.warning(f"[TRAILING_SL] {position_id} EXIT: {reason}")
            return True, reason
            
        return False, ""
        
    def remove_position(self, position_id: str) -> None:
        """Remove position from tracking (after exit)"""
        if position_id in self._peaks:
            del self._peaks[position_id]
            logger.debug(f"[TRAILING_SL] Removed position {position_id}")
            
    def get_position_stats(self, position_id: str) -> Optional[Dict[str, float]]:
        """Get trailing SL stats for a position"""
        if position_id not in self._peaks:
            return None
            
        data = self._peaks[position_id]
        entry = data["entry_price"]
        peak = data["peak_price"]
        
        return {
            "entry_price": entry,
            "peak_price": peak,
            "peak_gain_pct": (peak - entry) / entry,
            "trailing_active": data["activated_at"] is not None,
        }


# Singleton instance (can be imported globally)
_trailing_stop_manager: Optional[TrailingStopManager] = None


def get_trailing_stop_manager() -> TrailingStopManager:
    """Get or create the global trailing stop manager"""
    global _trailing_stop_manager
    if _trailing_stop_manager is None:
        _trailing_stop_manager = TrailingStopManager()
    return _trailing_stop_manager
