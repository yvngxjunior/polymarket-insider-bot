"""
Exit Manager — gestion automatique des sorties de position.

Surveille en continu toutes les positions EXECUTED et les ferme si:
  1. Take Profit partiel (TP1) → prix >= entrée * (1 + TP1_PCT) → VEND 50%
  2. Take Profit total  (TP2) → prix >= entrée * (1 + TP2_PCT) → VEND le reste
  3. Stop Loss          (SL)  → prix <= entrée * (1 - SL_PCT)  → VEND 100%
  4. Marché quasi-résolu     → prix > 0.95 ou < 0.05           → VEND 100%
  5. Durée max dépassée      → position ouverte > MAX_HOLD_HOURS → VEND 100%

Logique de vente partielle:
  - Au TP1 (+20%) : on vend 50% de la position → on sécurise du profit
  - Le reste court jusqu'au TP2 (+40%), SL, résolution ou durée max
  - En DRY RUN : simule tout, log + Telegram, zéro ordre réel

FIX BUG-2  — _partial_sold persisté en DB (colonne tp1_remaining sur CopiedTrade).
FIX BUG-3  — filtre SQL exclut les positions déjà CLOSED.
FIX EXIT-1 — filtre _check_positions() unifié DRY_RUN + LIVE.
FIX EXIT-2 — _get_current_price accepte maintenant le side (BUY/SELL)
               pour éviter le calcul de PnL faux sur les positions SELL.
FIX EXIT-3 — guard trade.id is None dans _check_positions
               pour éviter KeyError sur _partial_sold[None].
"""
import asyncio
from datetime import datetime
from typing import TYPE_CHECKING, Optional

import aiohttp
from sqlalchemy import text

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
    Implémente une stratégie de vente partielle:
      TP1 (+20%) → vend 50% | TP2 (+40%) → vend le reste | SL -30% → vend tout

    Source de vérité unique pour la fermeture des positions.
    PositionManager ne doit PAS appeler release_position() (cf. BUG-1).
    """

    TAKE_PROFIT1_PCT = 0.20
    TAKE_PROFIT2_PCT = 0.40
    STOP_LOSS_PCT    = 0.30
    MAX_HOLD_HOURS   = 72
    RESOLVING_THRESH = 0.95
    CHECK_INTERVAL   = 60
    PARTIAL_SELL_PCT = 0.50

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
        # FIX BUG-2: rechargé depuis DB au démarrage
        self._partial_sold: dict[int, float] = {}
        self._load_partial_sold()

    # ------------------------------------------------------------------
    # FIX BUG-2 — Persistance de _partial_sold
    # ------------------------------------------------------------------

    def _load_partial_sold(self) -> None:
        try:
            from bot.database import engine as db_engine
            with db_engine.connect() as conn:
                rows = conn.execute(
                    text(
                        "SELECT id, amount_usdc, skip_reason FROM copied_trades "
                        "WHERE status = 'executed' "
                        "AND skip_reason LIKE 'TP1_REMAINING:%'"
                    )
                ).fetchall()
            for row in rows:
                trade_id, amount_usdc, skip_reason = row
                try:
                    remaining = float(skip_reason.split("TP1_REMAINING:")[1])
                    self._partial_sold[int(trade_id)] = remaining
                except (IndexError, ValueError):
                    pass
            if self._partial_sold:
                logger.info(
                    f"[EXIT] Loaded {len(self._partial_sold)} TP1 partial state(s) from DB"
                )
        except Exception as e:
            logger.warning(f"[EXIT] Could not load partial sold state: {e}")

    def _persist_partial(self, trade_id: int, remaining: float) -> None:
        try:
            with get_db() as db:
                t = db.query(CopiedTrade).filter(CopiedTrade.id == trade_id).first()
                if t:
                    t.skip_reason = f"TP1_REMAINING:{remaining:.2f}"
        except Exception as e:
            logger.warning(f"[EXIT] Could not persist partial state for trade {trade_id}: {e}")

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

    async def _get_current_price(
        self, token_id: str, side: str = "BUY"
    ) -> Optional[float]:
        """
        Récupère le prix actuel du token pour le side donné.

        FIX EXIT-2: le side était hardcodé à BUY, ce qui donnait un prix
        incorrect (et donc un PnL/TP/SL faux) pour les positions SELL.
        On passe maintenant trade.side depuis _check_positions().
        """
        try:
            async with self._get_session().get(
                f"{settings.polymarket_host}/price",
                params={"token_id": token_id, "side": side.upper()},
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
        trade_id: int,
        entry_price: float,
        current_price: float,
        side: str,
        executed_at: Optional[datetime],
        amount_usdc: float,
    ) -> tuple[str, str, float]:
        """
        Détermine quelle action prendre.
        Returns: (action, reason, sell_amount_usdc)
          action: "PARTIAL" | "FULL" | "NONE"
        """
        if side.upper() == "BUY":
            pnl_pct = (current_price - entry_price) / entry_price
        else:
            pnl_pct = (entry_price - current_price) / entry_price

        already_partial = trade_id in self._partial_sold
        remaining = self._partial_sold.get(trade_id, amount_usdc)

        if pnl_pct <= -self.STOP_LOSS_PCT:
            return "FULL", f"SL {pnl_pct:.1%}", remaining

        if current_price >= self.RESOLVING_THRESH:
            return "FULL", f"Market resolving YES @ {current_price:.2f}", remaining
        if current_price <= (1.0 - self.RESOLVING_THRESH):
            return "FULL", f"Market resolving NO @ {current_price:.2f}", remaining

        if executed_at:
            age_h = (datetime.utcnow() - executed_at).total_seconds() / 3600
            if age_h >= self.MAX_HOLD_HOURS:
                return "FULL", f"Max hold {age_h:.0f}h", remaining

        if already_partial and pnl_pct >= self.TAKE_PROFIT2_PCT:
            return "FULL", f"TP2 +{pnl_pct:.1%}", remaining

        if not already_partial and pnl_pct >= self.TAKE_PROFIT1_PCT:
            partial_amount = round(amount_usdc * self.PARTIAL_SELL_PCT, 2)
            return "PARTIAL", f"TP1 +{pnl_pct:.1%} (50% sold)", partial_amount

        return "NONE", "", 0.0

    def _calc_pnl_usdc(
        self, entry: float, current: float, amount: float, side: str
    ) -> float:
        shares = amount / entry if entry > 0 else 0
        return shares * (current - entry if side.upper() == "BUY" else entry - current)

    # ------------------------------------------------------------------
    # Traitement d'un cycle de vérification
    # ------------------------------------------------------------------

    async def _check_positions(self) -> None:
        """
        FIX EXIT-1: filtre unifié DRY_RUN + LIVE via ~LIKE 'CLOSED%'.
        FIX EXIT-3: guard trade.id is None pour éviter KeyError sur _partial_sold.
        FIX EXIT-2: passe trade.side à _get_current_price().
        """
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
            # FIX EXIT-3: trade.id peut être None si non encore flushé
            if trade.id is None:
                logger.warning(
                    f"[EXIT] Skipping trade with id=None "
                    f"(token={trade.token_id[:16] if trade.token_id else '?'})"
                )
                continue

            # FIX EXIT-2: passe trade.side pour obtenir le bon prix
            current = await self._get_current_price(trade.token_id, side=trade.side)
            if current is None:
                continue

            action, reason, sell_amount = self._should_exit(
                trade_id=trade.id,
                entry_price=trade.price,
                current_price=current,
                side=trade.side,
                executed_at=trade.executed_at,
                amount_usdc=trade.amount_usdc,
            )

            if action == "NONE":
                continue

            pnl = self._calc_pnl_usdc(
                entry=trade.price,
                current=current,
                amount=sell_amount,
                side=trade.side,
            )

            is_partial = (action == "PARTIAL")
            dry_tag = "[DRY RUN] " if settings.dry_run else ""
            log_tag = "Partial close (TP1)" if is_partial else "Full close"

            logger.info(
                f"[EXIT] {dry_tag}{log_tag} "
                f"'{(trade.market_question or trade.token_id[:20])[:40]}' "
                f"| {reason} | sell=${sell_amount:.2f} | P&L {pnl:+.2f} USDC"
            )

            success = await self.engine.close_position(
                token_id=trade.token_id,
                entry_price=trade.price,
                amount_usdc=sell_amount,
                market_question=trade.market_question or "",
            )

            if not success:
                continue

            if is_partial:
                remaining = round(trade.amount_usdc - sell_amount, 2)
                self._partial_sold[trade.id] = remaining
                self._persist_partial(trade.id, remaining)
                self.risk_manager.apply_pnl(pnl=pnl)

                pnl_emoji = "🟢" if pnl >= 0 else "🔴"
                await self.notifier.send(
                    f"📄 <b>Partial Sell — TP1"
                    f"{'  (DRY RUN)' if settings.dry_run else ''}</b>\n"
                    f"────────────────────\n"
                    f"📊 <i>{(trade.market_question or trade.token_id[:20])[:60]}</i>\n"
                    f"💰 Sold: <b>${sell_amount:.2f} USDC (50%)</b>\n"
                    f"{pnl_emoji} P&amp;L partiel: <b>{pnl:+.2f} USDC</b>\n"
                    f"📈 Entry: {trade.price:.3f} → Now: {current:.3f}\n"
                    f"⏳ Remaining: <b>${remaining:.2f} USDC</b> running to TP2 (+40%)\n"
                    f"📝 Trigger: {reason}\n"
                )

            else:
                self.risk_manager.release_position(trade.token_id, pnl=pnl)
                was_partial = trade.id in self._partial_sold
                self._partial_sold.pop(trade.id, None)

                with get_db() as db:
                    t = db.query(CopiedTrade).filter(CopiedTrade.id == trade.id).first()
                    if t:
                        t.skip_reason = (
                            f"CLOSED{'(TP1+TP2)' if was_partial else ''}: "
                            f"{reason} | PnL {pnl:+.2f}"
                        )

                pnl_emoji = "🟢" if pnl >= 0 else "🔴"
                await self.notifier.send(
                    f"📤 <b>Position {'Closed' if not settings.dry_run else 'Closed (DRY RUN)'}</b>\n"
                    f"────────────────────\n"
                    f"📊 <i>{(trade.market_question or trade.token_id[:20])[:60]}</i>\n"
                    f"{pnl_emoji} P&amp;L: <b>{pnl:+.2f} USDC</b>\n"
                    f"📈 Entry: {trade.price:.3f} → Exit: {current:.3f}\n"
                    f"📝 Trigger: {reason}\n"
                )

    # ------------------------------------------------------------------
    # Boucle background
    # ------------------------------------------------------------------

    async def _loop(self) -> None:
        logger.info(
            f"[EXIT] Manager started — "
            f"TP1=+{self.TAKE_PROFIT1_PCT:.0%} (50%) | "
            f"TP2=+{self.TAKE_PROFIT2_PCT:.0%} (rest) | "
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
