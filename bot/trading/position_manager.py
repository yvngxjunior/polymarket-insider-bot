import asyncio
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

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
    Surveille les positions ouvertes et les ferme automatiquement.
    Stratégies: Take Profit, Stop Loss, Time Stop.

    NOTE: Ce composant est un monitor in-memory secondaire.
    La gestion réelle des fermetures (ordres SELL + DB) est assurée par ExitManager.
    PositionManager se charge uniquement de:
      - Maintenir le registre in-memory des positions
      - Déclencher release_position() dans le RiskManager quand une condition est atteinte
    """

    # FIX: TAKE_PROFIT_PCT est maintenant un multiplicateur relatif à l'entrée
    # Ancienne valeur 0.80 était comparée au prix absolu → TP se déclenchait
    # dès que le prix > 0.80 quelle que soit la mise.
    # Nouveau: TAKE_PROFIT_PCT = 0.40 → TP si current >= entry * 1.40 (+40%)
    TAKE_PROFIT_PCT = 0.40
    STOP_LOSS_PCT = 0.30
    MAX_AGE_HOURS = 72
    CHECK_INTERVAL = 30

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

    async def start_monitoring(self) -> None:
        logger.info("Position manager started.")
        while True:
            await asyncio.sleep(self.CHECK_INTERVAL)
            await self._check_all_positions()

    async def _check_all_positions(self) -> None:
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
        if pos.side == "BUY":
            # FIX: TP relatif à l'entrée, pas au prix absolu
            # Avant: current_price >= TAKE_PROFIT_PCT (0.80) → comparaison absurde
            # Maintenant: current_price >= entry_price * (1 + TAKE_PROFIT_PCT)
            if current_price >= pos.entry_price * (1 + self.TAKE_PROFIT_PCT):
                return f"✅ Take Profit @ {current_price:.3f} (+{self.TAKE_PROFIT_PCT:.0%} from entry {pos.entry_price:.3f})"
            loss_pct = (pos.entry_price - current_price) / pos.entry_price
            if loss_pct >= self.STOP_LOSS_PCT:
                return f"🛑 Stop Loss @ {current_price:.3f} (-{loss_pct:.0%})"
        if pos.age_hours >= self.MAX_AGE_HOURS:
            return f"⏰ Time Stop ({pos.age_hours:.0f}h open)"
        return None

    async def _close_position(
        self, pos: OpenPosition, current_price: float, reason: str
    ) -> None:
        estimated_pnl = (current_price - pos.entry_price) * pos.amount_usdc
        logger.info(
            f"📤 Closing position: {reason} | "
            f"Market: {pos.market_question[:40]} | P&L: ${estimated_pnl:+.2f}"
        )
        # FIX: on ne double-ferme plus la position en LIVE.
        # ExitManager gère déjà les ordres SELL → PositionManager se contente
        # de libérer sa propre référence in-memory + notifier.
        # release_position() est appelé ici uniquement pour le monitor in-memory;
        # ExitManager appelle aussi release_position() via son propre flow.
        # En pratique PositionManager et ExitManager sont redondants:
        # ExitManager est le composant autoritaire, PositionManager est un fallback.
        self.risk.release_position(pos.token_id, pnl=estimated_pnl)
        self._positions.pop(pos.token_id, None)
        msg = (
            f"📤 <b>Position Closed</b>\n"
            f"<i>{pos.market_question[:60]}</i>\n"
            f"Reason: {reason}\n"
            f"P&L: <b>${estimated_pnl:+.2f}</b>\n"
            f"Entry: {pos.entry_price:.3f} → Exit: {current_price:.3f}"
        )
        await self.notifier.send(msg)

    async def _get_current_price(self, token_id: str) -> Optional[float]:
        # FIX: utilise /price (singulier) — l'ancien code utilisait /prices
        # qui n'existe pas → 404 en permanence → aucune position jamais fermée.
        try:
            resp = await self.client._data_client.get(
                "/price", params={"token_id": token_id, "side": "BUY"}
            )
            if resp.status_code == 200:
                return float(resp.json().get("price", 0))
        except Exception as e:
            logger.debug(f"Price fetch failed for {token_id[:16]}...: {e}")
        return None
