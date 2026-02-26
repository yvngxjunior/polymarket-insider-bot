"""
Position Sizer — Kelly fractionnaire standalone.
Utilisé pour les signaux LLM et arbitrage.

Formule Kelly: f* = (p * (b+1) - 1) / b
  où p = win_rate estimé, b = (1-price)/price
  On applique Quarter-Kelly (f* * 0.25) pour limiter la variance.

FIX BUG-8: PositionSizer._capital est désormais synchronisé avec
  RiskManager.portfolio.total_capital avant chaque calcul via sync_capital().
  L'ancienne version gardait un capital figé depuis le démarrage, ce qui
  sous-estimait ou surestimait le sizing au fil des gains/pertes.
"""
from dataclasses import dataclass

from bot.config import get_settings
from bot.utils.logger import logger

settings = get_settings()

_DEFAULT_CAPITAL = getattr(settings, "initial_capital", None) or settings.max_trade_amount * 10


@dataclass
class SizeResult:
    amount_usdc: float
    pct_of_capital: float
    kelly_fraction: float
    rationale: str


class PositionSizer:
    KELLY_FRACTION = 0.25
    MIN_TRADE_USDC = 2.0

    def __init__(self, capital_usdc: float = 0.0) -> None:
        self._capital = capital_usdc if capital_usdc > 0 else _DEFAULT_CAPITAL

    def update_capital(self, capital_usdc: float) -> None:
        """Met à jour le capital de référence pour les prochains calculs."""
        if capital_usdc > 0:
            self._capital = capital_usdc

    def sync_capital(self, risk_manager) -> None:
        """
        FIX BUG-8: synchronise le capital depuis RiskManager.portfolio.total_capital.
        À appeler dans process_new_trade() avant chaque calculate().
        """
        try:
            cap = risk_manager.portfolio.total_capital
            if cap > 0:
                self._capital = cap
        except Exception:
            pass

    def calculate(
        self,
        yes_price: float,
        conviction_score: float,
        source_amount: float = 0.0,
    ) -> SizeResult:
        if not (0.01 <= yes_price <= 0.99):
            return SizeResult(
                amount_usdc=self.MIN_TRADE_USDC,
                pct_of_capital=0.0,
                kelly_fraction=0.0,
                rationale=f"Invalid price {yes_price:.3f}",
            )

        p = max(0.01, min(0.99, conviction_score))
        b = (1.0 - yes_price) / yes_price

        full_kelly = (p * (b + 1) - 1) / b if b > 0 else 0.0
        fraction = max(0.0, full_kelly * self.KELLY_FRACTION)
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
                f"${final_amount:.2f} (ratio {ratio:.2f}x source) capital=${self._capital:.0f}"
            )
        else:
            rationale = (
                f"Kelly({conviction_score:.0%}) p={p:.2f} b={b:.2f} → "
                f"${final_amount:.2f} ({pct:.1%} capital=${self._capital:.0f})"
            )

        logger.debug(f"[SIZER] {rationale}")
        return SizeResult(
            amount_usdc=final_amount,
            pct_of_capital=round(pct, 4),
            kelly_fraction=round(fraction, 4),
            rationale=rationale,
        )
