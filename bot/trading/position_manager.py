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

    FIX BUG-1 — PositionManager N'EST PLUS la source de vérité pour les fermetures.
    ExitManager est le seul composant autorisé à appeler release_position() sur
    le RiskManager. PositionManager maintient uniquement son registre in-memory
    et envoie des alertes Telegram — il ne touche PLUS au RiskManager.

    FIX BUG-7 — start_monitoring() a été intentionnellement désactivé.
    La boucle de monitoring crée une double-fermeture avec ExitManager (BUG-1).
    Ce composant est conservé pour register() (utilisé dans main.py pour le
    guard "position déjà ouverte") mais la boucle active est supprimée.
    Si PositionManager doit être réactivé à l'avenir, il faudra:
      1. Supprimer l'appel à release_position() dans _close_position()
      2. Coordonner avec ExitManager via un flag partagé
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
        logger.info(f"📌 Position registered: {market_question[:40]} @ {entry_price:.3f}")

    def unregister(self, token_id: str) -> None:
        """Appelé par ExitManager après une fermeture réelle pour nettoyer le registre."""
        self._positions.pop(token_id, None)

    def is_open(self, token_id: str) -> bool:
        return token_id in self._positions

    # start_monitoring() volontairement absent — voir docstring.
    # Ne pas réintroduire sans résoudre BUG-1 proprement.
