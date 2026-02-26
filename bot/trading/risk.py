from dataclasses import dataclass, field
from datetime import date, datetime
from enum import Enum

from sqlalchemy import text

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
    """
    État du portefeuille.
    Tous les defaults sont lus depuis settings (zéro hardcode).
    """
    total_capital: float = field(default_factory=lambda: settings.initial_capital)
    daily_pnl: float = 0.0
    daily_reset_date: date = field(default_factory=date.today)
    peak_capital: float = field(default_factory=lambda: settings.initial_capital)
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
    Gestionnaire de risques — Kelly Criterion + limites dynamiques.
    Toutes les constantes sont lues depuis settings (zéro hardcode).

    Paramètres configurables dans .env :
      INITIAL_CAPITAL         Capital de départ (défaut: 500)
      MAX_POSITIONS           Positions simultanées max (défaut: 10)
      DAILY_LOSS_LIMIT_PCT    Perte journalière max % (défaut: 0.15)
      DRAWDOWN_LIMIT_PCT      Drawdown max depuis le pic % (défaut: 0.25)
      KELLY_FRACTION          Fraction Kelly (défaut: 0.25 = Quarter-Kelly)
      CONVERGENCE_BOOST       Multiplicateur convergence (défaut: 1.5)
    """

    # ── Properties alias → settings.* (zéro hardcode, rétro-compatibilité) ──
    @property
    def MAX_POSITIONS(self) -> int:
        return settings.max_positions

    @property
    def DAILY_LOSS_LIMIT_PCT(self) -> float:
        return settings.daily_loss_limit_pct

    @property
    def DRAWDOWN_LIMIT_PCT(self) -> float:
        return settings.drawdown_limit_pct

    @property
    def KELLY_FRACTION(self) -> float:
        return settings.kelly_fraction

    @property
    def CONVERGENCE_BOOST(self) -> float:
        return settings.convergence_boost

    def __init__(self, initial_capital: float | None = None):
        if initial_capital is None:
            initial_capital = settings.initial_capital
        self._open_positions: set[str] = set()
        self.portfolio = PortfolioState(
            total_capital=initial_capital,
            peak_capital=initial_capital,
        )
        self._load_from_db()

    def _load_from_db(self) -> None:
        try:
            from bot.database import engine
            with engine.connect() as conn:
                row = conn.execute(
                    text(
                        "SELECT total_capital, peak_capital, daily_pnl, "
                        "daily_reset_date, open_positions_csv "
                        "FROM portfolio_snapshot WHERE id=1"
                    )
                ).fetchone()
            if row:
                self.portfolio.total_capital = float(row[0] or settings.initial_capital)
                self.portfolio.peak_capital  = float(row[1] or row[0] or settings.initial_capital)
                self.portfolio.daily_pnl     = float(row[2] or 0.0)
                try:
                    stored_date = row[3]
                    if stored_date:
                        if isinstance(stored_date, date):
                            self.portfolio.daily_reset_date = stored_date
                        else:
                            self.portfolio.daily_reset_date = date.fromisoformat(
                                str(stored_date)[:10]
                            )
                except Exception:
                    pass
                csv = row[4] or ""
                self._open_positions = {
                    t.strip() for t in csv.split(",") if t.strip()
                }
                logger.info(
                    f"[RISK] Loaded from DB — capital=${self.portfolio.total_capital:.2f} "
                    f"peak=${self.portfolio.peak_capital:.2f} "
                    f"open={len(self._open_positions)} positions"
                )
        except Exception as e:
            logger.warning(f"[RISK] Could not load from DB (first run?): {e}")

    def _persist(self) -> None:
        """UPSERT portable SQLite + PostgreSQL."""
        try:
            from bot.database import engine
            csv = ",".join(self._open_positions)
            now = datetime.utcnow().isoformat()
            params = {
                "cap":  self.portfolio.total_capital,
                "peak": self.portfolio.peak_capital,
                "dpnl": self.portfolio.daily_pnl,
                "drd":  self.portfolio.daily_reset_date.isoformat(),
                "csv":  csv,
                "now":  now,
            }
            with engine.connect() as conn:
                result = conn.execute(
                    text(
                        "UPDATE portfolio_snapshot SET "
                        "total_capital=:cap, peak_capital=:peak, daily_pnl=:dpnl, "
                        "daily_reset_date=:drd, open_positions_csv=:csv, "
                        "updated_at=:now WHERE id=1"
                    ),
                    params,
                )
                if result.rowcount == 0:
                    conn.execute(
                        text(
                            "INSERT INTO portfolio_snapshot "
                            "(id, total_capital, peak_capital, daily_pnl, "
                            "daily_reset_date, open_positions_csv, updated_at) "
                            "VALUES (1, :cap, :peak, :dpnl, :drd, :csv, :now)"
                        ),
                        params,
                    )
                    logger.warning(
                        "[RISK] portfolio_snapshot row was missing — inserted seed row."
                    )
                conn.commit()
        except Exception as e:
            logger.warning(f"[RISK] Persist error: {e}")

    def evaluate(
        self,
        token_id: str,
        price: float,
        source_amount: float,
        source_wallet_balance: float = 1000.0,
        wallet_win_rate: float = 0.70,
        is_convergence_signal: bool = False,
        market_volume_usdc: float = 0.0,
    ) -> TradeDecision:
        self.portfolio.reset_daily_if_needed()

        if price > settings.max_price:
            return TradeDecision(False, 0, RejectReason.PRICE_TOO_HIGH.value)
        if price < settings.min_price:
            return TradeDecision(False, 0, RejectReason.PRICE_TOO_LOW.value)

        if market_volume_usdc > 0 and market_volume_usdc < 1_000:
            return TradeDecision(False, 0, RejectReason.LOW_LIQUIDITY.value)

        daily_loss_limit = -self.portfolio.total_capital * settings.daily_loss_limit_pct
        if self.portfolio.daily_pnl <= daily_loss_limit:
            return TradeDecision(False, 0, RejectReason.DAILY_LOSS_LIMIT.value)
        if self.portfolio.drawdown_pct >= settings.drawdown_limit_pct:
            return TradeDecision(False, 0, RejectReason.DRAWDOWN.value)
        if len(self._open_positions) >= settings.max_positions:
            return TradeDecision(False, 0, RejectReason.MAX_POSITIONS.value)
        if token_id in self._open_positions:
            return TradeDecision(False, 0, RejectReason.DUPLICATE.value)

        kelly_fraction = self._kelly_sizing(win_rate=wallet_win_rate, price=price)
        kelly_amount = round_usdc(self.portfolio.total_capital * kelly_fraction)

        if is_convergence_signal:
            kelly_amount = round_usdc(kelly_amount * settings.convergence_boost)
            logger.info(f"🔥 Convergence boost applied: x{settings.convergence_boost}")

        final_amount = round_usdc(min(kelly_amount, settings.max_trade_amount))
        if final_amount < settings.min_trade_usdc:
            return TradeDecision(False, 0, RejectReason.AMOUNT_TOO_SMALL.value)

        return TradeDecision(
            approved=True,
            amount_usdc=final_amount,
            kelly_fraction=kelly_fraction,
        )

    def _kelly_sizing(self, win_rate: float, price: float) -> float:
        win_rate = max(0.0, min(1.0, win_rate))
        if price <= 0 or price >= 1:
            return 0.01
        b = (1 - price) / price
        full_kelly = (win_rate * (b + 1) - 1) / b
        quarter_kelly = max(0, full_kelly * settings.kelly_fraction)
        return min(quarter_kelly, settings.max_position_pct)

    def register_position(self, token_id: str) -> None:
        self._open_positions.add(token_id)
        self.portfolio.open_positions_count = len(self._open_positions)
        self._persist()

    def apply_pnl(self, pnl: float = 0.0) -> None:
        self.portfolio.update_capital(pnl)
        self._persist()
        logger.info(
            f"[RISK] Partial PnL applied: ${pnl:+.2f} | "
            f"Capital: ${self.portfolio.total_capital:.2f} | "
            f"Open: {len(self._open_positions)}"
        )

    def release_position(self, token_id: str, pnl: float = 0.0) -> None:
        self._open_positions.discard(token_id)
        self.portfolio.update_capital(pnl)
        self.portfolio.open_positions_count = len(self._open_positions)
        self._persist()
        logger.info(
            f"Position closed. P&L: ${pnl:+.2f} | "
            f"Capital: ${self.portfolio.total_capital:.2f} | "
            f"Drawdown: {self.portfolio.drawdown_pct:.1%}"
        )
