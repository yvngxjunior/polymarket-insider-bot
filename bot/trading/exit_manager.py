"""
Exit Manager — gestion automatique des sorties de position.

Surveille en continu toutes les positions EXECUTED et les ferme si:
  1. Take Profit atteint   → prix actuel >= entrée * (1 + TP_PCT)
  2. Stop Loss atteint     → prix actuel <= entrée * (1 - SL_PCT)
  3. Marché quasi-résolu   → prix > 0.95 (YES) ou < 0.05 (NO)
  4. Durée max dépassée    → position ouverte > MAX_HOLD_HOURS

En DRY RUN : simule la fermeture, log + Telegram, pas d'ordre réel.
En LIVE    : appelle engine.close_position() → ordre SELL signé sur Polygon.
"""
import asyncio
from datetime import datetime
from typing import TYPE_CHECKING, Optional

import aiohttp

from bot.config import get_settings
from bot.database import get_db, CopiedTrade, TradeStatus
from bot.trading.risk import RiskManager
from bot.notifications.telegram import TelegramNotifier
from bot.utils.logger import logger

if TYPE_CHECKING:
    from bot.trading.engine import TradingEngine

settings = get_settings()


class ExitManager:
    """
    Background task de surveillance et fermeture automatique des positions.
    """

    TAKE_PROFIT_PCT  = 0.20    # +20% → Take Profit
    STOP_LOSS_PCT    = 0.30    # -30% → Stop Loss
    MAX_HOLD_HOURS   = 72      # 72h max de détention
    RESOLVING_THRESH = 0.95    # Prix > 95% ou < 5% → résolution imminente
    CHECK_INTERVAL   = 60      # Vérifie toutes les 60s

    def __init__(
        self,
        risk_manager: RiskManager,
        notifier: TelegramNotifier,
        engine: "TradingEngine",
    ) -> None:
        self.risk_manager = risk_manager
        self.notifier = notifier
        self.engine = engine
        self._session: Optional[aiohttp.ClientSession] = None
        self._running = False
        self._task: Optional[asyncio.Task] = None

    # ------------------------------------------------------------------
    # Session HTTP
    # ------------------------------------------------------------------
    def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=8)
            )
        return self._session

    # ------------------------------------------------------------------
    # Prix actuel d'un token
    # ------------------------------------------------------------------
    async def _get_current_price(self, token_id: str) -> Optional[float]:
        try:
            async with self._get_session().get(
                f"{settings.polymarket_host}/price",
                params={"token_id": token_id, "side": "BUY"},
            ) as resp:
                if resp.status == 200:
                    return float((await resp.json()).get("price", 0))
        except Exception as e:
            logger.debug(f"[EXIT] Price fetch {token_id[:8]}: {e}")
        return None

    # ------------------------------------------------------------------
    # Logique de décision de sortie
    # ------------------------------------------------------------------
    def _should_exit(
        self,
        entry_price: float,
        current_price: float,
        side: str,
        executed_at: Optional[datetime],
    ) -> tuple[bool, str]:
        if side.upper() == "BUY":
            pnl_pct = (current_price - entry_price) / entry_price
        else:
            pnl_pct = (entry_price - current_price) / entry_price

        if pnl_pct >= self.TAKE_PROFIT_PCT:
            return True, f"TP +{pnl_pct:.1%}"
        if pnl_pct <= -self.STOP_LOSS_PCT:
            return True, f"SL {pnl_pct:.1%}"
        if current_price >= self.RESOLVING_THRESH:
            return True, f"Market resolving YES @ {current_price:.2f}"
        if current_price <= (1.0 - self.RESOLVING_THRESH):
            return True, f"Market resolving NO @ {current_price:.2f}"
        if executed_at:
            age_h = (datetime.utcnow() - executed_at).total_seconds() / 3600
            if age_h >= self.MAX_HOLD_HOURS:
                return True, f"Max hold {age_h:.0f}h"

        return False, ""

    def _calc_pnl_usdc(
        self, entry: float, current: float, amount: float, side: str
    ) -> float:
        shares = amount / entry if entry > 0 else 0
        return shares * (current - entry if side.upper() == "BUY" else entry - current)

    # ------------------------------------------------------------------
    # Traitement d'un cycle de vérification
    # ------------------------------------------------------------------
    async def _check_positions(self) -> None:
        with get_db() as db:
            open_trades = (
                db.query(CopiedTrade)
                .filter(
                    CopiedTrade.status == TradeStatus.EXECUTED,
                    CopiedTrade.skip_reason.in_(["DRY_RUN", None])
                    if settings.dry_run
                    else CopiedTrade.tx_hash != None,  # noqa: E711
                )
                .all()
            )

        for trade in open_trades:
            current = await self._get_current_price(trade.token_id)
            if current is None:
                continue

            close, reason = self._should_exit(
                entry_price=trade.price,
                current_price=current,
                side=trade.side,
                executed_at=trade.executed_at,
            )
            if not close:
                continue

            pnl = self._calc_pnl_usdc(
                entry=trade.price,
                current=current,
                amount=trade.amount_usdc,
                side=trade.side,
            )

            logger.info(
                f"[EXIT] {'[DRY RUN] ' if settings.dry_run else ''}"
                f"Closing {trade.side} ‘{(trade.market_question or trade.token_id[:20])[:40]}’ "
                f"| {reason} | P&L {pnl:+.2f} USDC"
            )

            # ── Exécute la fermeture ──
            success = await self.engine.close_position(
                token_id=trade.token_id,
                entry_price=trade.price,
                amount_usdc=trade.amount_usdc,
                market_question=trade.market_question or "",
            )

            if success:
                # Libère la position dans le RiskManager (capital mis à jour)
                self.risk_manager.release_position(trade.token_id, pnl=pnl)

                # Marque la position comme clôturée en DB
                with get_db() as db:
                    t = db.query(CopiedTrade).filter(CopiedTrade.id == trade.id).first()
                    if t:
                        t.skip_reason = f"CLOSED: {reason} | PnL {pnl:+.2f}"

                # Notification Telegram
                pnl_emoji = "🟢" if pnl >= 0 else "🔴"
                await self.notifier.send(
                    f"📤 <b>Position {'Closed' if not settings.dry_run else 'Closed (DRY RUN)'}</b>\n"
                    f"────────────────────\n"
                    f"📊 <i>{(trade.market_question or trade.token_id[:20])[:60]}</i>\n"
                    f"{pnl_emoji} P&L: <b>{pnl:+.2f} USDC</b>\n"
                    f"📈 Entry: {trade.price:.3f} → Exit: {current:.3f}\n"
                    f"📝 Trigger: {reason}\n"
                )

    # ------------------------------------------------------------------
    # Boucle background
    # ------------------------------------------------------------------
    async def _loop(self) -> None:
        logger.info(
            f"[EXIT] Manager started — "
            f"TP=+{self.TAKE_PROFIT_PCT:.0%} | "
            f"SL=-{self.STOP_LOSS_PCT:.0%} | "
            f"MaxHold={self.MAX_HOLD_HOURS}h | "
            f"Check every {self.CHECK_INTERVAL}s"
        )
        while self._running:
            try:
                await self._check_positions()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"[EXIT] Loop error: {e}")
            await asyncio.sleep(self.CHECK_INTERVAL)

    async def start(self) -> None:
        self._running = True
        self._task = asyncio.create_task(self._loop())

    async def stop(self) -> None:
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        if self._session and not self._session.closed:
            await self._session.close()
