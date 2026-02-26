from dataclasses import dataclass, field
from datetime import date
from enum import Enum

from bot.config import get_settings
from bot.utils.helpers import round_usdc
from bot.utils.logger import logger

settings = get_settings()


class RejectReason(Enum):
    PRICE_TOO_HIGH = "Price too high (market likely resolved)"
    PRICE_TOO_LOW = "Price too low (too risky)"
    AMOUNT_TOO_SMALL = "Amount after sizing below minimum"
    DUPLICATE = "Duplicate trade already open"
    DAILY_LOSS_LIMIT = "Daily loss limit reached"
    MAX_POSITIONS = "Max concurrent positions reached"
    DRAWDOWN = "Portfolio drawdown limit reached"
    LOW_LIQUIDITY = "Market liquidity too low"


@dataclass
class TradeDecision:
    approved: bool
    amount_usdc: float
    reason: str = ""
    kelly_fraction: float = 0.0


@dataclass
class PortfolioState:
    total_capital: float = 500.0
    daily_pnl: float = 0.0
    daily_reset_date: date = field(default_factory=date.today)
    peak_capital: float = 500.0
    open_positions_count: int = 0

    @property
    def drawdown_pct(self) -> float:
        if self.peak_capital <= 0:
            return 0.0
        return (self.peak_capital - self.total_capital) / self.peak_capital

    def update_capital(self, delta: float) -> None:
        self.total_capital += delta
        self.daily_pnl += delta
        if self.total_capital > self.peak_capital:
            self.peak_capital = self.total_capital

    def reset_daily_if_needed(self) -> None:
        today = date.today()
        if self.daily_reset_date != today:
            self.daily_reset_date = today
            self.daily_pnl = 0.0
            logger.info(f"📅 Daily P&L reset. Capital: ${self.total_capital:.2f}")


class RiskManager:
    """
    Gestionnaire de risques v2 — Kelly Criterion + limites dynamiques.
    Kelly formula: f* = (p*(b+1) - 1) / b
    On applique Quarter-Kelly (f* * 0.25) pour limiter la variance.
    """

    MAX_POSITIONS = 10
    DAILY_LOSS_LIMIT_PCT = 0.15
    DRAWDOWN_LIMIT_PCT = 0.25
    KELLY_FRACTION = 0.25
    CONVERGENCE_BOOST = 1.5

    def __init__(self, initial_capital: float = 500.0):
        self._open_positions: set[str] = set()
        self.portfolio = PortfolioState(total_capital=initial_capital)

    def evaluate(
        self,
        token_id: str,
        price: float,
        source_amount: float,
        source_wallet_balance: float = 1000.0,
        wallet_win_rate: float = 0.70,
        is_convergence_signal: bool = False,
        market_volume_usdc: float = 10_000.0,
    ) -> TradeDecision:
        self.portfolio.reset_daily_if_needed()

        if price > settings.max_price:
            return TradeDecision(False, 0, RejectReason.PRICE_TOO_HIGH.value)
        if price < settings.min_price:
            return TradeDecision(False, 0, RejectReason.PRICE_TOO_LOW.value)
        if market_volume_usdc < 1_000:
            return TradeDecision(False, 0, RejectReason.LOW_LIQUIDITY.value)

        daily_loss_limit = -self.portfolio.total_capital * self.DAILY_LOSS_LIMIT_PCT
        if self.portfolio.daily_pnl <= daily_loss_limit:
            return TradeDecision(False, 0, RejectReason.DAILY_LOSS_LIMIT.value)
        if self.portfolio.drawdown_pct >= self.DRAWDOWN_LIMIT_PCT:
            return TradeDecision(False, 0, RejectReason.DRAWDOWN.value)
        if len(self._open_positions) >= self.MAX_POSITIONS:
            return TradeDecision(False, 0, RejectReason.MAX_POSITIONS.value)
        if token_id in self._open_positions:
            return TradeDecision(False, 0, RejectReason.DUPLICATE.value)

        kelly_fraction = self._kelly_sizing(win_rate=wallet_win_rate, price=price)
        kelly_amount = round_usdc(self.portfolio.total_capital * kelly_fraction)

        if is_convergence_signal:
            kelly_amount = round_usdc(kelly_amount * self.CONVERGENCE_BOOST)
            logger.info(f"🔥 Convergence boost applied: x{self.CONVERGENCE_BOOST}")

        final_amount = round_usdc(min(kelly_amount, settings.max_trade_amount))
        if final_amount < 1.0:
            return TradeDecision(False, 0, RejectReason.AMOUNT_TOO_SMALL.value)

        return TradeDecision(approved=True, amount_usdc=final_amount, kelly_fraction=kelly_fraction)

    def _kelly_sizing(self, win_rate: float, price: float) -> float:
        if price <= 0 or price >= 1:
            return 0.01
        b = (1 - price) / price
        full_kelly = (win_rate * (b + 1) - 1) / b
        quarter_kelly = max(0, full_kelly * self.KELLY_FRACTION)
        return min(quarter_kelly, settings.max_position_pct)

    def register_position(self, token_id: str) -> None:
        self._open_positions.add(token_id)
        self.portfolio.open_positions_count = len(self._open_positions)

    def apply_pnl(self, pnl: float = 0.0) -> None:
        """Crédite/débite le PnL sans fermer la position (utilisé pour le TP1 partiel)."""
        self.portfolio.update_capital(pnl)
        logger.info(
            f"[RISK] Partial PnL applied: ${pnl:+.2f} | "
            f"Capital: ${self.portfolio.total_capital:.2f} | "
            f"Open: {len(self._open_positions)}"
        )

    def release_position(self, token_id: str, pnl: float = 0.0) -> None:
        self._open_positions.discard(token_id)
        self.portfolio.update_capital(pnl)
        self.portfolio.open_positions_count = len(self._open_positions)
        logger.info(
            f"Position closed. P&L: ${pnl:+.2f} | "
            f"Capital: ${self.portfolio.total_capital:.2f} | "
            f"Drawdown: {self.portfolio.drawdown_pct:.1%}"
        )
