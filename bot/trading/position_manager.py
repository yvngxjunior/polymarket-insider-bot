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
    """

    TAKE_PROFIT_PCT = 0.80
    STOP_LOSS_PCT = 0.40
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
        if pos.side == "BUY" and current_price >= self.TAKE_PROFIT_PCT:
            return f"✅ Take Profit @ {current_price:.3f}"
        if pos.side == "BUY":
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
        if not settings.dry_run:
            pass  # ExitManager handles LIVE sells via engine.close_position()
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
        try:
            resp = await self.client._data_client.get(
                "/prices", params={"token_id": token_id}
            )
            if resp.status_code == 200:
                return float(resp.json().get("price", 0))
        except Exception as e:
            logger.debug(f"Price fetch failed for {token_id[:16]}...: {e}")
        return None
