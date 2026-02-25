import asyncio
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from bot.config import get_settings
from bot.database import get_db, CopiedTrade, TradeStatus
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
    Surveille les positions ouvertes et les ferme automatiquement.

    Stratégies de sortie implémentées:
      1. Take Profit: sortie si prix atteint TAKE_PROFIT_PCT du max théorique
      2. Stop Loss: sortie si prix chute de STOP_LOSS_PCT depuis l'entrée
      3. Time Stop: sortie si position ouverte depuis plus de MAX_AGE_HOURS
         (évite d'être bloqué sur un marché qui ne se résout pas)

    Ces règles transforment le bot en système actif de gestion du capital.
    """

    TAKE_PROFIT_PCT = 0.80   # Vendre quand le prix atteint 80% de la cote
    STOP_LOSS_PCT = 0.40     # Couper si prix tombe à -40% de l'entrée
    MAX_AGE_HOURS = 72       # Sortir si position ouverte depuis 72h
    CHECK_INTERVAL = 30      # Vérification toutes les 30 secondes

    def __init__(
        self,
        client: PolymarketDataClient,
        risk_manager: RiskManager,
        notifier: TelegramNotifier,
    ):
        self.client = client
        self.risk = risk_manager
        self.notifier = notifier
        self._positions: dict[str, OpenPosition] = {}  # token_id -> position

    def register(
        self,
        trade_id: int,
        token_id: str,
        entry_price: float,
        amount_usdc: float,
        side: str,
        market_question: str = "",
    ) -> None:
        """Enregistre une nouvelle position ouverte."""
        self._positions[token_id] = OpenPosition(
            trade_id=trade_id,
            token_id=token_id,
            entry_price=entry_price,
            amount_usdc=amount_usdc,
            side=side,
            market_question=market_question,
            opened_at=datetime.utcnow(),
        )
        logger.info(f"📌 Position registered: {market_question[:40]} @ {entry_price:.3f}")

    async def start_monitoring(self) -> None:
        """Lance la boucle de surveillance des positions (tâche asyncio background)."""
        logger.info("Position manager started.")
        while True:
            await asyncio.sleep(self.CHECK_INTERVAL)
            await self._check_all_positions()

    async def _check_all_positions(self) -> None:
        """Vérifie chaque position ouverte contre les critères de sortie."""
        if not self._positions:
            return

        for token_id, pos in list(self._positions.items()):
            try:
                current_price = await self._get_current_price(token_id)
                if current_price is None:
                    continue

                exit_reason = self._should_exit(pos, current_price)
                if exit_reason:
                    await self._close_position(pos, current_price, exit_reason)

            except Exception as e:
                logger.error(f"Position check error for {token_id[:16]}...: {e}")

    def _should_exit(self, pos: OpenPosition, current_price: float) -> Optional[str]:
        """Retourne la raison de sortie ou None si on garde la position."""
        # Take profit
        if pos.side == "BUY" and current_price >= self.TAKE_PROFIT_PCT:
            return f"✅ Take Profit @ {current_price:.3f}"

        # Stop loss
        if pos.side == "BUY":
            loss_pct = (pos.entry_price - current_price) / pos.entry_price
            if loss_pct >= self.STOP_LOSS_PCT:
                return f"🛑 Stop Loss @ {current_price:.3f} (-{loss_pct:.0%})"

        # Time stop
        if pos.age_hours >= self.MAX_AGE_HOURS:
            return f"⏰ Time Stop ({pos.age_hours:.0f}h open)"

        return None

    async def _close_position(
        self,
        pos: OpenPosition,
        current_price: float,
        reason: str
    ) -> None:
        """Ferme une position (en DRY RUN = log seulement)."""
        estimated_pnl = (current_price - pos.entry_price) * pos.amount_usdc

        logger.info(
            f"📤 Closing position: {reason} | "
            f"Market: {pos.market_question[:40]} | "
            f"P&L: ${estimated_pnl:+.2f}"
        )

        if not settings.dry_run:
            # TODO: Implémenter l'ordre de vente CLOB
            pass

        # Libérer la position dans le risk manager
        self.risk.release_position(pos.token_id, pnl=estimated_pnl)

        # Retirer du suivi
        self._positions.pop(pos.token_id, None)

        # Notification
        msg = (
            f"📤 <b>Position Closed</b>\n"
            f"<i>{pos.market_question[:60]}</i>\n"
            f"Reason: {reason}\n"
            f"P&L: <b>${estimated_pnl:+.2f}</b>\n"
            f"Entry: {pos.entry_price:.3f} → Exit: {current_price:.3f}"
        )
        await self.notifier.send(msg)

    async def _get_current_price(
        self,
        token_id: str
    ) -> Optional[float]:
        """Récupère le prix actuel d'un token via l'API Polymarket."""
        try:
            # Utilise l'endpoint midpoint du CLOB
            resp = await self.client._data_client.get(
                "/prices",
                params={"token_id": token_id}
            )
            if resp.status_code == 200:
                data = resp.json()
                return float(data.get("price", 0))
        except Exception as e:
            logger.debug(f"Price fetch failed for {token_id[:16]}...: {e}")
        return None
