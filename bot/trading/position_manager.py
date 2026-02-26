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
    L'ancienne version ne consultait que _positions (dict in-memory, vide
    apres restart) -> toutes les positions semblaient fermees au redemarrage
    -> risque de double-entry sur un token deja en portefeuille.
    Correction: _load_open_positions() au __init__ reconstitue le dict
    depuis copied_trades (executed + NOT CLOSED). is_open() garde le
    lookup O(1) in-memory en premier, puis fallback DB si necessaire.
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
        Reconstitue _positions avec des OpenPosition minimaux (pas de trade_id
        complet, mais suffisant pour le guard is_open() dans main.py).
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
        self._positions[token_id] = OpenPosition(
            trade_id=trade_id, token_id=token_id, entry_price=entry_price,
            amount_usdc=amount_usdc, side=side, market_question=market_question,
            opened_at=datetime.utcnow(),
        )
        logger.info(f"Position registered: {market_question[:40]} @ {entry_price:.3f}")

    def unregister(self, token_id: str) -> None:
        """Appele par ExitManager apres une fermeture reelle pour nettoyer le registre."""
        self._positions.pop(token_id, None)

    def is_open(self, token_id: str) -> bool:
        """
        FIX PM-1: lookup in-memory O(1) en premier.
        Si absent (dict pas encore peuple apres un register() manque),
        fallback vers la DB pour securite anti-double-entry.
        """
        if token_id in self._positions:
            return True
        # Fallback DB: verifie si un trade EXECUTED non CLOSED existe pour ce token
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
            logger.warning(f"[POS] DB is_open fallback failed for {token_id[:20]}: {e}")
            return False

    # start_monitoring() volontairement absent -- voir docstring.
    # Ne pas reintroduire sans resoudre BUG-1 proprement.
