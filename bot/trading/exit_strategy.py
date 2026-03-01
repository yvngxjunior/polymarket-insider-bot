"""Exit Strategy v1.0 - Position exit logic with Trailing SL integration"""
from typing import Optional, Tuple
from datetime import datetime, timedelta

from bot.trading.trailing_stop import get_trailing_stop_manager, TrailingStopConfig
from bot.utils.logger import logger


class ExitStrategy:
    """Manages position exit logic with multiple strategies"""
    
    def __init__(
        self,
        use_trailing_sl: bool = True,
        fixed_tp1: float = 0.20,  # +20% take profit 1
        fixed_tp2: float = 0.35,  # +35% take profit 2
        fixed_sl: float = -0.30,  # -30% stop loss (only if trailing disabled)
        max_hold_hours: int = 48,  # Max 48h hold time
    ):
        self.use_trailing_sl = use_trailing_sl
        self.fixed_tp1 = fixed_tp1
        self.fixed_tp2 = fixed_tp2
        self.fixed_sl = fixed_sl
        self.max_hold_hours = max_hold_hours
        
        # Get trailing SL manager if enabled
        self.trailing_manager = get_trailing_stop_manager() if use_trailing_sl else None
        
    def check_exit(
        self,
        position_id: str,
        entry_price: float,
        current_price: float,
        entry_time: datetime,
    ) -> Tuple[bool, str, Optional[float]]:
        """
        Check if position should exit.
        
        Returns:
            (should_exit, reason, exit_price)
        """
        current_gain_pct = (current_price - entry_price) / entry_price
        hold_time = datetime.utcnow() - entry_time
        
        # 1. Check Take Profit levels
        if current_gain_pct >= self.fixed_tp2:
            return True, f"TP2 hit @ {current_gain_pct:+.1%}", current_price
            
        if current_gain_pct >= self.fixed_tp1:
            # Partial exit at TP1, but let trailing SL handle the rest
            if self.use_trailing_sl:
                logger.info(
                    f"[EXIT] {position_id} reached TP1 ({current_gain_pct:+.1%}), "
                    f"trailing SL now active"
                )
                # Continue holding with trailing protection
            else:
                return True, f"TP1 hit @ {current_gain_pct:+.1%}", current_price
                
        # 2. Check Trailing Stop-Loss (if enabled)
        if self.use_trailing_sl and self.trailing_manager:
            should_exit, reason = self.trailing_manager.should_exit(
                position_id, current_price
            )
            if should_exit:
                return True, reason, current_price
                
        # 3. Check Fixed Stop-Loss (if trailing disabled)
        if not self.use_trailing_sl and current_gain_pct <= self.fixed_sl:
            return True, f"Fixed SL hit @ {current_gain_pct:+.1%}", current_price
            
        # 4. Check Max Hold Time
        if hold_time > timedelta(hours=self.max_hold_hours):
            return (
                True,
                f"Max hold time reached ({hold_time.total_seconds() / 3600:.1f}h)",
                current_price,
            )
            
        # No exit condition met
        return False, "", None
        
    def register_position(
        self,
        position_id: str,
        entry_price: float,
    ) -> None:
        """Register new position for tracking"""
        if self.use_trailing_sl and self.trailing_manager:
            self.trailing_manager.register_position(position_id, entry_price)
            
    def on_position_closed(self, position_id: str) -> None:
        """Clean up after position is closed"""
        if self.use_trailing_sl and self.trailing_manager:
            self.trailing_manager.remove_position(position_id)
            
    def get_position_stats(self, position_id: str) -> dict:
        """Get current stats for a position"""
        if self.use_trailing_sl and self.trailing_manager:
            stats = self.trailing_manager.get_position_stats(position_id)
            if stats:
                return stats
                
        return {}
