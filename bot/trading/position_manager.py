from dataclasses import dataclass
from datetime import datetime

from bot.config import get_settings
from bot.trading.polymarket import PolymarketDataClient
from bot.trading.risk import RiskManager
from bot.notifications.telegram import TelegramNotifier
from bot.utils.logger import logger

settings = get_settings()


@dataclass
class OpenPosition:
    trade_id: int
    token_id: str
    entry_price: float
    amount_usdc: float
    side: str
    market_question: str
    opened_at: datetime

    @property
    def age_hours(self) -> float:
        return (datetime.utcnow() - self.opened_at).total_seconds() / 3600


class PositionManager:
    """
    Registre in-memory des positions ouvertes.

    FIX BUG-1 -- PositionManager N'EST PLUS la source de verite pour les fermetures.
    ExitManager est le seul composant autorise a appeler release_position() sur
    le RiskManager. PositionManager maintient uniquement son registre in-memory
    et envoie des alertes Telegram -- il ne touche PLUS au RiskManager.

    FIX BUG-7 -- start_monitoring() a ete intentionnellement desactive.
    La boucle de monitoring cree une double-fermeture avec ExitManager (BUG-1).
    Ce composant est conserve pour register() + is_open() (utilises dans main.py)
    mais la boucle active est supprimee.

    FIX PM-1 -- is_open() fallback DB + rechargement au demarrage.
    FIX PM-2 -- register() guard entry_price <= 0.
    FIX PM-3 -- is_open() fallback DB log debug (hot path, pas de spam).
    """

    TAKE_PROFIT_PCT = 0.40
    STOP_LOSS_PCT = 0.30
    MAX_AGE_HOURS = 72

    def __init__(
        self,
        client: PolymarketDataClient,
        risk_manager: RiskManager,
        notifier: TelegramNotifier,
    ):
        self.client = client
        self.risk = risk_manager
        self.notifier = notifier
        self._positions: dict[str, OpenPosition] = {}
        # FIX PM-1: reconstitue le registre depuis la DB au demarrage
        self._load_open_positions()

    # ------------------------------------------------------------------
    # FIX PM-1 -- Chargement initial depuis DB
    # ------------------------------------------------------------------

    def _load_open_positions(self) -> None:
        """
        Recharge les positions ouvertes depuis copied_trades au demarrage.
        Critères: status=EXECUTED et skip_reason NOT LIKE 'CLOSED%'.
        """
        try:
            from bot.database import get_db, CopiedTrade, TradeStatus
            with get_db() as db:
                open_trades = (
                    db.query(CopiedTrade)
                    .filter(
                        CopiedTrade.status == TradeStatus.EXECUTED,
                        ~CopiedTrade.skip_reason.like("CLOSED%"),
                    )
                    .all()
                )
            for trade in open_trades:
                if trade.token_id and trade.token_id not in self._positions:
                    self._positions[trade.token_id] = OpenPosition(
                        trade_id=trade.id,
                        token_id=trade.token_id,
                        entry_price=trade.price or 0.0,
                        amount_usdc=trade.amount_usdc or 0.0,
                        side=trade.side or "BUY",
                        market_question=trade.market_question or "",
                        opened_at=trade.executed_at or trade.created_at or datetime.utcnow(),
                    )
            if self._positions:
                logger.info(
                    f"[POS] Loaded {len(self._positions)} open position(s) from DB "
                    f"(restart recovery)"
                )
        except Exception as e:
            logger.warning(f"[POS] Could not load open positions from DB: {e}")

    # ------------------------------------------------------------------
    # API publique
    # ------------------------------------------------------------------

    def register(
        self,
        trade_id: int,
        token_id: str,
        entry_price: float,
        amount_usdc: float,
        side: str,
        market_question: str = "",
    ) -> None:
        # FIX PM-2: guard entry_price invalide
        if entry_price <= 0:
            logger.warning(
                f"[POS] register() called with entry_price={entry_price} "
                f"token={token_id[:20]}... — position enregistrée avec prix nul, "
                f"ExitManager ne pourra pas calculer le PnL correctement."
            )
        self._positions[token_id] = OpenPosition(
            trade_id=trade_id, token_id=token_id, entry_price=entry_price,
            amount_usdc=amount_usdc, side=side, market_question=market_question,
            opened_at=datetime.utcnow(),
        )
        logger.info(
            f"[POS] Position registered: {market_question[:40] or token_id[:20]} "
            f"@ {entry_price:.3f} ${amount_usdc:.2f}"
        )

    def unregister(self, token_id: str) -> None:
        """Appelé par ExitManager après une fermeture réelle pour nettoyer le registre."""
        removed = self._positions.pop(token_id, None)
        if removed:
            logger.debug(f"[POS] Unregistered: {token_id[:20]}")

    def is_open(self, token_id: str) -> bool:
        """
        FIX PM-1: lookup in-memory O(1) en premier.
        Si absent, fallback vers la DB pour sécurité anti-double-entry.
        FIX PM-3: fallback log debug (pas warning) → pas de spam sur le hot path.
        """
        if token_id in self._positions:
            return True
        # Fallback DB: vérifie si un trade EXECUTED non CLOSED existe pour ce token
        try:
            from bot.database import get_db, CopiedTrade, TradeStatus
            with get_db() as db:
                exists = (
                    db.query(CopiedTrade.id)
                    .filter(
                        CopiedTrade.token_id == token_id,
                        CopiedTrade.status == TradeStatus.EXECUTED,
                        ~CopiedTrade.skip_reason.like("CLOSED%"),
                    )
                    .first()
                )
                return exists is not None
        except Exception as e:
            # FIX PM-3: debug (pas warning) — ce path est appelé à chaque trade scan
            logger.debug(f"[POS] DB is_open fallback failed for {token_id[:20]}: {e}")
            return False

    # start_monitoring() volontairement absent -- voir docstring.
    # Ne pas réintroduire sans résoudre BUG-1 proprement.
