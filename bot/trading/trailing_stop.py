"""
Trailing Stop-Loss v1.0
========================
Stop-loss dynamique qui suit le prix max atteint (ATH de la position).
Maximise les profits en laissant courir les winners.

Features:
- Trailing stop basé sur ATH position
- Configurable trailing distance (% du ATH)
- Lock-in profits après seuils
- Compatible avec exit_manager.py
"""
from dataclasses import dataclass
from typing import Optional

from bot.utils.logger import logger


@dataclass
class TrailingStopConfig:
    """Configuration trailing stop."""
    enabled: bool = True
    initial_stop_pct: float = 0.30  # Stop initial à -30%
    trailing_distance_pct: float = 0.15  # Trail à 15% du ATH
    lock_profit_threshold: float = 0.25  # Lock profits à +25%
    lock_profit_stop_pct: float = 0.10  # Stop à +10% après lock


class TrailingStop:
    """
    Gère trailing stop-loss dynamique pour une position.
    
    Logique:
    1. Position ouvre à $0.50
    2. Prix monte à $0.70 (+40%)
    3. ATH = $0.70, stop trail à $0.595 (-15% du ATH)
    4. Prix redescend à $0.60 → pas touché
    5. Prix à $0.59 → STOP TRIGGERED, sell
    """
    
    def __init__(
        self,
        entry_price: float,
        config: Optional[TrailingStopConfig] = None,
    ):
        self.entry_price = entry_price
        self.config = config or TrailingStopConfig()
        
        # Tracking
        self.ath_price = entry_price  # All-time high de la position
        self.current_stop_price = entry_price * (1 - self.config.initial_stop_pct)
        self.profit_locked = False
        
        logger.debug(
            f"[TRAILING] Init: entry=${entry_price:.3f}, "
            f"initial_stop=${self.current_stop_price:.3f}"
        )
    
    def update(self, current_price: float) -> dict:
        """
        Update trailing stop avec nouveau prix.
        
        Args:
            current_price: Prix actuel du token
        
        Returns:
            Dict avec status:
            - triggered: bool (stop touché?)
            - stop_price: float (niveau stop actuel)
            - ath_price: float (ATH position)
            - pnl_pct: float (PnL actuel)
        """
        if not self.config.enabled:
            return {
                "triggered": False,
                "stop_price": self.current_stop_price,
                "ath_price": self.ath_price,
                "pnl_pct": (current_price - self.entry_price) / self.entry_price,
            }
        
        # Update ATH
        if current_price > self.ath_price:
            self.ath_price = current_price
            
            # Calcule nouveau trailing stop
            new_stop = self.ath_price * (1 - self.config.trailing_distance_pct)
            
            # Stop peut seulement monter, jamais descendre
            if new_stop > self.current_stop_price:
                self.current_stop_price = new_stop
                logger.debug(
                    f"[TRAILING] ATH updated: ${self.ath_price:.3f} → "
                    f"stop=${self.current_stop_price:.3f}"
                )
        
        # Lock-in profits si seuil atteint
        pnl_pct = (current_price - self.entry_price) / self.entry_price
        if (
            not self.profit_locked
            and pnl_pct >= self.config.lock_profit_threshold
        ):
            self.profit_locked = True
            # Stop ne peut pas descendre en dessous de entry + lock%
            locked_stop = self.entry_price * (1 + self.config.lock_profit_stop_pct)
            if locked_stop > self.current_stop_price:
                self.current_stop_price = locked_stop
                logger.info(
                    f"[TRAILING] Profit locked at +{pnl_pct:.0%} → "
                    f"stop=${self.current_stop_price:.3f}"
                )
        
        # Vérifie si stop touché
        triggered = current_price <= self.current_stop_price
        
        if triggered:
            logger.info(
                f"[TRAILING] STOP TRIGGERED: price=${current_price:.3f} ≤ "
                f"stop=${self.current_stop_price:.3f} (ATH=${self.ath_price:.3f})"
            )
        
        return {
            "triggered": triggered,
            "stop_price": self.current_stop_price,
            "ath_price": self.ath_price,
            "pnl_pct": pnl_pct,
        }
    
    def should_exit(self, current_price: float) -> bool:
        """
        Vérifie si position doit être fermée.
        
        Args:
            current_price: Prix actuel
        
        Returns:
            True si stop touché
        """
        result = self.update(current_price)
        return result["triggered"]
    
    def get_stop_distance(self) -> float:
        """
        Retourne distance actuelle entre ATH et stop (%).
        """
        if self.ath_price == 0:
            return 0.0
        return (self.ath_price - self.current_stop_price) / self.ath_price
    
    def to_dict(self) -> dict:
        """Sérialise state pour DB."""
        return {
            "entry_price": self.entry_price,
            "ath_price": self.ath_price,
            "current_stop_price": self.current_stop_price,
            "profit_locked": self.profit_locked,
            "stop_distance_pct": self.get_stop_distance(),
        }
    
    @classmethod
    def from_dict(cls, data: dict, config: Optional[TrailingStopConfig] = None) -> "TrailingStop":
        """Désérialise depuis DB."""
        stop = cls(entry_price=data["entry_price"], config=config)
        stop.ath_price = data.get("ath_price", stop.entry_price)
        stop.current_stop_price = data.get("current_stop_price", stop.current_stop_price)
        stop.profit_locked = data.get("profit_locked", False)
        return stop


class TrailingStopManager:
    """
    Gère trailing stops pour toutes les positions ouvertes.
    Intègre avec ExitManager.
    """
    
    def __init__(self, config: Optional[TrailingStopConfig] = None):
        self.config = config or TrailingStopConfig()
        self.stops: dict[str, TrailingStop] = {}  # token_id -> TrailingStop
    
    def add_position(
        self,
        token_id: str,
        entry_price: float,
    ) -> None:
        """Ajoute nouvelle position avec trailing stop."""
        if token_id in self.stops:
            logger.warning(f"[TRAILING] Position {token_id[:12]} already tracked")
            return
        
        self.stops[token_id] = TrailingStop(
            entry_price=entry_price,
            config=self.config,
        )
        logger.info(f"[TRAILING] Added position {token_id[:12]} at ${entry_price:.3f}")
    
    def update_position(
        self,
        token_id: str,
        current_price: float,
    ) -> Optional[dict]:
        """
        Update position avec nouveau prix.
        
        Returns:
            Dict avec status si position existe, None sinon
        """
        if token_id not in self.stops:
            return None
        
        return self.stops[token_id].update(current_price)
    
    def should_exit_position(self, token_id: str, current_price: float) -> bool:
        """
        Vérifie si position doit être fermée.
        """
        if token_id not in self.stops:
            return False
        
        return self.stops[token_id].should_exit(current_price)
    
    def remove_position(self, token_id: str) -> None:
        """Retire position du tracking."""
        if token_id in self.stops:
            del self.stops[token_id]
            logger.debug(f"[TRAILING] Removed position {token_id[:12]}")
    
    def get_all_stops(self) -> dict:
        """Retourne tous les stops actifs."""
        return {
            token_id: stop.to_dict()
            for token_id, stop in self.stops.items()
        }
    
    def clear(self) -> None:
        """Clear tous les stops."""
        self.stops.clear()
        logger.info("[TRAILING] All stops cleared")


if __name__ == "__main__":
    # Test trailing stop
    print("Testing Trailing Stop...\n")
    
    config = TrailingStopConfig(
        initial_stop_pct=0.30,
        trailing_distance_pct=0.15,
        lock_profit_threshold=0.25,
    )
    
    stop = TrailingStop(entry_price=0.50, config=config)
    
    # Simule mouvement de prix
    prices = [0.55, 0.60, 0.70, 0.75, 0.80, 0.75, 0.70, 0.68, 0.65]
    
    for price in prices:
        result = stop.update(price)
        print(
            f"Price: ${price:.2f} | "
            f"Stop: ${result['stop_price']:.3f} | "
            f"ATH: ${result['ath_price']:.2f} | "
            f"PnL: {result['pnl_pct']:+.0%} | "
            f"Triggered: {result['triggered']}"
        )
        
        if result["triggered"]:
            print("\n⚠️ STOP TRIGGERED - Position closed\n")
            break
    
    print("\n✅ Trailing stop test complete")
