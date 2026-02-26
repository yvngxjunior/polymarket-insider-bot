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
    Implémente une stratégie de vente partielle:
      TP1 (+20%) → vend 50% | TP2 (+40%) → vend le reste | SL -30% → vend tout
    """

    TAKE_PROFIT1_PCT = 0.20    # +20% → TP1 partiel (50% vendus)
    TAKE_PROFIT2_PCT = 0.40    # +40% → TP2 final   (100% du restant vendus)
    STOP_LOSS_PCT    = 0.30    # -30% → Stop Loss total
    MAX_HOLD_HOURS   = 72      # 72h max de détention
    RESOLVING_THRESH = 0.95    # Prix > 95% ou < 5% → résolution imminente
    CHECK_INTERVAL   = 60      # Vérifie toutes les 60s
    PARTIAL_SELL_PCT = 0.50    # Fraction vendue au TP1

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
        # Suit les positions dont le TP1 a déjà été exécuté {trade_id: remaining_amount}
        self._partial_sold: dict[int, float] = {}

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
        trade_id: int,
        entry_price: float,
        current_price: float,
        side: str,
        executed_at: Optional[datetime],
        amount_usdc: float,
    ) -> tuple[str, str, float]:
        """
        Détermine quelle action prendre.

        Returns:
            (action, reason, sell_amount_usdc)
            action: "PARTIAL" | "FULL" | "NONE"
        """
        if side.upper() == "BUY":
            pnl_pct = (current_price - entry_price) / entry_price
        else:
            pnl_pct = (entry_price - current_price) / entry_price

        already_partial = trade_id in self._partial_sold
        # Montant restant (après TP1 éventuel)
        remaining = self._partial_sold.get(trade_id, amount_usdc)

        # ── Stop Loss — toujours vend TOUT (même si TP1 déjà exécuté) ──
        if pnl_pct <= -self.STOP_LOSS_PCT:
            return "FULL", f"SL {pnl_pct:.1%}", remaining

        # ── Marché quasi-résolu ──
        if current_price >= self.RESOLVING_THRESH:
            return "FULL", f"Market resolving YES @ {current_price:.2f}", remaining
        if current_price <= (1.0 - self.RESOLVING_THRESH):
            return "FULL", f"Market resolving NO @ {current_price:.2f}", remaining

        # ── Durée max ──
        if executed_at:
            age_h = (datetime.utcnow() - executed_at).total_seconds() / 3600
            if age_h >= self.MAX_HOLD_HOURS:
                return "FULL", f"Max hold {age_h:.0f}h", remaining

        # ── TP2 (uniquement si TP1 déjà exécuté) ──
        if already_partial and pnl_pct >= self.TAKE_PROFIT2_PCT:
            return "FULL", f"TP2 +{pnl_pct:.1%}", remaining

        # ── TP1 (uniquement si pas encore fait) ──
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
        # FIX: filtre SQLAlchemy séparé pour éviter le tuple implicite
        # L'ancienne syntaxe créait un tuple (condition, condition) au lieu
        # d'une branche if/else, ce qui faisait tout passer en mode LIVE.
        filter_cond = (
            CopiedTrade.skip_reason.in_(["DRY_RUN", None])
            if settings.dry_run
            else CopiedTrade.tx_hash != None  # noqa: E711
        )
        with get_db() as db:
            open_trades = (
                db.query(CopiedTrade)
                .filter(
                    CopiedTrade.status == TradeStatus.EXECUTED,
                    filter_cond,
                )
                .all()
            )

        for trade in open_trades:
            current = await self._get_current_price(trade.token_id)
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

            # ── Exécution ──
            success = await self.engine.close_position(
                token_id=trade.token_id,
                entry_price=trade.price,
                amount_usdc=sell_amount,
                market_question=trade.market_question or "",
            )

            if not success:
                continue

            if is_partial:
                # ── TP1 exécuté : met à jour le montant restant ──
                remaining = round(trade.amount_usdc - sell_amount, 2)
                self._partial_sold[trade.id] = remaining

                # FIX: apply_pnl() au lieu de release_position() pour le TP1 partiel.
                # release_position() retirait le token de _open_positions, permettant
                # au bot de ré-entrer immédiatement alors que la position est encore ouverte.
                self.risk_manager.apply_pnl(pnl=pnl)

                pnl_emoji = "🟢" if pnl >= 0 else "🔴"
                await self.notifier.send(
                    f"📄 <b>Partial Sell — TP1"
                    f"{'  (DRY RUN)' if settings.dry_run else ''}</b>\n"
                    f"────────────────────\n"
                    f"📊 <i>{(trade.market_question or trade.token_id[:20])[:60]}</i>\n"
                    f"💰 Sold: <b>${sell_amount:.2f} USDC (50%)</b>\n"
                    f"{pnl_emoji} P&L partiel: <b>{pnl:+.2f} USDC</b>\n"
                    f"📈 Entry: {trade.price:.3f} → Now: {current:.3f}\n"
                    f"⏳ Remaining: <b>${remaining:.2f} USDC</b> running to TP2 (+40%)\n"
                    f"📝 Trigger: {reason}\n"
                )

            else:
                # ── Fermeture totale ──
                self.risk_manager.release_position(trade.token_id, pnl=pnl)

                # FIX: was_partial doit être évalué AVANT le .pop()
                # Avant: was_partial était vérifié après le pop → toujours False
                # → le tag "(TP1+TP2)" n'était jamais écrit en DB.
                was_partial = trade.id in self._partial_sold
                self._partial_sold.pop(trade.id, None)

                # Marque la position comme clôturée en DB
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
