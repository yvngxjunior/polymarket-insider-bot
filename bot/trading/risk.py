from dataclasses import dataclass
from enum import Enum

from bot.config import get_settings
from bot.utils.helpers import round_usdc
from bot.utils.logger import logger

settings = get_settings()


class RejectReason(Enum):
    PRICE_TOO_HIGH = "Price too high (market likely resolved)"
    PRICE_TOO_LOW = "Price too low (too risky)"
    AMOUNT_TOO_SMALL = "Amount after sizing below minimum"
    DRY_RUN = "DRY_RUN mode active"
    DUPLICATE = "Duplicate trade already open"


@dataclass
class TradeDecision:
    approved: bool
    amount_usdc: float
    reason: str = ""


class RiskManager:
    """
    Valide et ajuste chaque trade avant exécution.

    Règles appliquées:
      1. Le prix doit être entre MIN_PRICE et MAX_PRICE
      2. Le montant est plafonné à MAX_TRADE_AMOUNT
      3. Le montant minimum est 1 USDC
      4. En DRY_RUN, les trades sont loggués mais pas exécutés
    """

    def __init__(self):
        self._open_positions: set[str] = set()  # token_ids en cours

    def evaluate(
        self,
        token_id: str,
        price: float,
        source_amount: float,
        source_wallet_balance: float = 1000.0,
    ) -> TradeDecision:
        """
        Évalue si un trade doit être exécuté et pour quel montant.

        Args:
            token_id: ID du token sur Polymarket
            price: Prix actuel du token (0.0 — 1.0)
            source_amount: Montant misé par le wallet source
            source_wallet_balance: Capital estimé du wallet source
        """
        # Check prix hors limites
        if price > settings.max_price:
            return TradeDecision(
                approved=False,
                amount_usdc=0,
                reason=RejectReason.PRICE_TOO_HIGH.value
            )
        if price < settings.min_price:
            return TradeDecision(
                approved=False,
                amount_usdc=0,
                reason=RejectReason.PRICE_TOO_LOW.value
            )

        # Sizing proportionnel au wallet source
        if source_wallet_balance > 0:
            position_pct = source_amount / source_wallet_balance
            sized_amount = round_usdc(
                min(
                    position_pct * (settings.max_trade_amount / settings.max_position_pct),
                    settings.max_trade_amount
                )
            )
        else:
            sized_amount = round_usdc(min(source_amount, settings.max_trade_amount))

        if sized_amount < 1.0:
            return TradeDecision(
                approved=False,
                amount_usdc=0,
                reason=RejectReason.AMOUNT_TOO_SMALL.value
            )

        # Check duplicate
        if token_id in self._open_positions:
            return TradeDecision(
                approved=False,
                amount_usdc=0,
                reason=RejectReason.DUPLICATE.value
            )

        return TradeDecision(approved=True, amount_usdc=sized_amount)

    def register_position(self, token_id: str) -> None:
        self._open_positions.add(token_id)

    def release_position(self, token_id: str) -> None:
        self._open_positions.discard(token_id)
