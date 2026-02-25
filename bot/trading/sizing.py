"""
Position Sizer — inspiré de dexorynlabs/polymarket-trading-bot-python

Calcule la taille de position optimale via Kelly fractionnaire.
Utilisé comme calculateur standalone pour les signaux LLM et arbitrage
(le RiskManager interne du TradingEngine gère déjà Kelly pour le copy trading).

Formule Kelly:
  f* = (p * (b+1) - 1) / b
  où p = win_rate estimé, b = (1-price)/price (odds nettes)
  On applique Quarter-Kelly (f* * 0.25) pour limiter la variance.
"""
from dataclasses import dataclass

from bot.config import get_settings
from bot.utils.logger import logger

settings = get_settings()


@dataclass
class SizeResult:
    amount_usdc: float
    pct_of_capital: float
    kelly_fraction: float
    rationale: str


class PositionSizer:
    """
    Calculateur Kelly standalone.
    Peut être utilisé indépendamment du TradingEngine pour estimer
    la taille optimale d'un trade avant de l'envoyer au moteur.
    """

    KELLY_FRACTION = 0.25    # Quarter-Kelly (conservateur)
    MIN_TRADE_USDC = 2.0     # Minimum absolu pour éviter les micro-trades

    def __init__(self, capital_usdc: float = 0.0) -> None:
        # Capital de référence — peut être mis à jour dynamiquement
        self._capital = capital_usdc if capital_usdc > 0 else settings.max_trade_amount * 10

    def update_capital(self, capital_usdc: float) -> None:
        """Met à jour le capital de référence (appeler après chaque trade clôturé)."""
        if capital_usdc > 0:
            self._capital = capital_usdc

    def calculate(
        self,
        yes_price: float,
        conviction_score: float,
        source_amount: float = 0.0,
    ) -> SizeResult:
        """
        Calcule la taille de position optimale.

        Args:
            yes_price:        Prix du token YES (0.01 - 0.99)
            conviction_score: Score de confiance 0.0-1.0
                              (win_rate insider OU confidence LLM)
            source_amount:    Montant du trade source (pour calcul du ratio)

        Returns:
            SizeResult avec amount_usdc capped sur max_trade_amount
        """
        if not (0.01 <= yes_price <= 0.99):
            return SizeResult(
                amount_usdc=self.MIN_TRADE_USDC,
                pct_of_capital=0.0,
                kelly_fraction=0.0,
                rationale=f"Invalid price {yes_price:.3f}",
            )

        p = max(0.01, min(0.99, conviction_score))
        q = 1.0 - p
        b = (1.0 - yes_price) / yes_price  # odds nettes

        full_kelly = (p * (b + 1) - 1) / b if b > 0 else 0.0
        fraction = max(0.0, full_kelly * self.KELLY_FRACTION)

        # Cap sur max_position_pct du capital
        fraction = min(fraction, settings.max_position_pct)

        kelly_amount = self._capital * fraction
        final_amount = max(
            self.MIN_TRADE_USDC,
            min(kelly_amount, settings.max_trade_amount),
        )
        final_amount = round(final_amount, 2)
        pct = final_amount / self._capital if self._capital > 0 else 0.0

        if source_amount > 0:
            ratio = final_amount / source_amount
            rationale = (
                f"Kelly({conviction_score:.0%}) p={p:.2f} b={b:.2f} → "
                f"${final_amount:.2f} (ratio {ratio:.2f}x source)"
            )
        else:
            rationale = (
                f"Kelly({conviction_score:.0%}) p={p:.2f} b={b:.2f} → "
                f"${final_amount:.2f} ({pct:.1%} capital)"
            )

        logger.debug(f"[SIZER] {rationale}")
        return SizeResult(
            amount_usdc=final_amount,
            pct_of_capital=round(pct, 4),
            kelly_fraction=round(fraction, 4),
            rationale=rationale,
        )
