"""
Commandes Telegram interactives — PolyInsider Bot v2.4
=======================================================
Permet de contrôler le bot depuis Telegram sans toucher au serveur.

Commandes disponibles:
  /status     — état général (mode, wallets actifs, positions ouvertes)
  /pnl        — P&L du jour + total
  /positions  — liste des positions ouvertes
  /stop       — arrête le bot proprement (envoie signal SIGTERM)
  /setlive    — bascule DRY RUN → LIVE (demande confirmation)
  /whitelist  — ajoute un wallet à la whitelist
  /blacklist  — ajoute un wallet à la blacklist
  /help       — liste des commandes

Usage dans main.py:
  cmd_handler = CommandHandler(notifier=notifier, ...)
  await cmd_handler.start_polling()
  ...
  await cmd_handler.stop()
"""
from __future__ import annotations

import asyncio
import os
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

from bot.config import get_settings
from bot.database import get_db, CopiedTrade, TrackedWallet, TradeStatus
from bot.notifications.telegram import TelegramNotifier
from bot.utils.logger import logger

if TYPE_CHECKING:
    from bot.trading.risk import RiskManager
    from bot.analytics.performance import PerformanceTracker

settings = get_settings()


class BotCommandHandler:
    """
    Gère les commandes Telegram entrantes via long-polling.

    Args:
        notifier:            TelegramNotifier (pour envoyer les réponses)
        risk_manager:        RiskManager (positions ouvertes)
        performance_tracker: PerformanceTracker (P&L)
        stop_callback:       coroutine async appelée par /stop
    """

    def __init__(
        self,
        notifier: TelegramNotifier,
        risk_manager: "RiskManager",
        performance_tracker: "PerformanceTracker",
        stop_callback=None,
    ) -> None:
        self.notifier = notifier
        self.risk_manager = risk_manager
        self.performance_tracker = performance_tracker
        self.stop_callback = stop_callback
        self._app: Application | None = None
        self._task: asyncio.Task | None = None
        self._pending_setlive = False   # attend confirmation /setlive confirm

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def start_polling(self) -> None:
        """Démarre le polling Telegram en background."""
        self._app = (
            Application.builder()
            .token(settings.telegram_bot_token)
            .build()
        )
        self._register_handlers()
        await self._app.initialize()
        await self._app.start()
        await self._app.updater.start_polling(drop_pending_updates=True)
        logger.info("[COMMANDS] Telegram command polling started")

    async def stop(self) -> None:
        """Arrête proprement le polling."""
        if self._app:
            await self._app.updater.stop()
            await self._app.stop()
            await self._app.shutdown()
            logger.info("[COMMANDS] Telegram command polling stopped")

    def _register_handlers(self) -> None:
        assert self._app is not None
        for cmd, fn in [
            ("start",      self._cmd_help),
            ("help",       self._cmd_help),
            ("status",     self._cmd_status),
            ("pnl",        self._cmd_pnl),
            ("positions",  self._cmd_positions),
            ("stop",       self._cmd_stop),
            ("setlive",    self._cmd_setlive),
            ("whitelist",  self._cmd_whitelist),
            ("blacklist",  self._cmd_blacklist),
        ]:
            self._app.add_handler(CommandHandler(cmd, fn))

    # ------------------------------------------------------------------
    # Helper: répond dans le chat
    # ------------------------------------------------------------------

    async def _reply(self, update: Update, text: str) -> None:
        if update.message:
            await update.message.reply_html(text)

    # ------------------------------------------------------------------
    # /help
    # ------------------------------------------------------------------

    async def _cmd_help(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        await self._reply(update, (
            "🤖 <b>PolyInsider Bot — Commandes</b>\n"
            "────────────────────\n"
            "/status     — État du bot\n"
            "/pnl        — P&L du jour + total\n"
            "/positions  — Positions ouvertes\n"
            "/stop       — Arrêter le bot\n"
            "/setlive    — Passer en mode LIVE\n"
            "/whitelist [adresse]  — Forcer le suivi\n"
            "/blacklist [adresse]  — Blacklister un wallet\n"
        ))

    # ------------------------------------------------------------------
    # /status
    # ------------------------------------------------------------------

    async def _cmd_status(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        mode = "🟡 DRY RUN" if settings.dry_run else "🟢 LIVE"

        with get_db() as db:
            active_wallets = db.query(TrackedWallet).filter(
                TrackedWallet.is_active == True  # noqa: E712
            ).count()
            open_positions = db.query(CopiedTrade).filter(
                CopiedTrade.status == TradeStatus.EXECUTED
            ).count()

        capital = getattr(self.risk_manager, "_available_capital", 0.0)
        exposed = getattr(self.risk_manager, "_exposed_capital", 0.0)

        await self._reply(update, (
            f"🤖 <b>Bot Status</b>\n"
            f"────────────────────\n"
            f"Mode: <b>{mode}</b>\n"
            f"👥 Wallets actifs: <b>{active_wallets}</b>\n"
            f"📂 Positions ouvertes: <b>{open_positions}</b>\n"
            f"💰 Capital dispo: <b>${capital:,.2f}</b>\n"
            f"📉 Capital exposé: <b>${exposed:,.2f}</b>\n"
            f"⏱ Scan: <b>{settings.scan_interval}s</b>\n"
        ))

    # ------------------------------------------------------------------
    # /pnl
    # ------------------------------------------------------------------

    async def _cmd_pnl(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        try:
            stats = await self.performance_tracker.get_summary()
        except Exception:
            stats = {}

        total_pnl   = stats.get("total_pnl_usdc", 0.0)
        win_rate    = stats.get("win_rate", 0.0)
        total_trades = stats.get("total_trades", 0)
        pnl_emoji   = "🟢" if total_pnl >= 0 else "🔴"

        # P&L du jour
        today = datetime.now(timezone.utc).date()
        with get_db() as db:
            today_trades = db.query(CopiedTrade).filter(
                CopiedTrade.status == TradeStatus.EXECUTED,
            ).all()
            today_pnl = sum(
                float(getattr(t, "pnl_usdc", 0) or 0)
                for t in today_trades
                if t.executed_at and t.executed_at.date() == today
            )

        today_emoji = "🟢" if today_pnl >= 0 else "🔴"

        await self._reply(update, (
            f"💹 <b>P&amp;L Report</b>\n"
            f"────────────────────\n"
            f"{today_emoji} Aujourd'hui: <b>{today_pnl:+.2f} USDC</b>\n"
            f"{pnl_emoji} Total: <b>{total_pnl:+.2f} USDC</b>\n"
            f"🎯 Win rate: <b>{win_rate:.1%}</b>\n"
            f"🔄 Trades: <b>{total_trades}</b>\n"
        ))

    # ------------------------------------------------------------------
    # /positions
    # ------------------------------------------------------------------

    async def _cmd_positions(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        with get_db() as db:
            positions = db.query(CopiedTrade).filter(
                CopiedTrade.status == TradeStatus.EXECUTED
            ).order_by(CopiedTrade.executed_at.desc()).limit(10).all()

        if not positions:
            await self._reply(update, "📦 Aucune position ouverte.")
            return

        lines = ["📂 <b>Positions ouvertes</b>\n────────────────────"]
        for p in positions:
            age = ""
            if p.executed_at:
                hours = (datetime.utcnow() - p.executed_at).total_seconds() / 3600
                age = f" ({hours:.0f}h)"
            question = (p.market_question or p.token_id or "?")[:35]
            lines.append(
                f"\u2022 <i>{question}</i>\n"
                f"  {p.side} ${p.amount_usdc:.0f} @ {p.price:.3f}{age}"
            )
        await self._reply(update, "\n".join(lines))

    # ------------------------------------------------------------------
    # /stop
    # ------------------------------------------------------------------

    async def _cmd_stop(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        await self._reply(update, "🛑 <b>Arrêt demandé…</b> Le bot va s'arrêter proprement.")
        logger.warning("[COMMANDS] /stop received via Telegram")
        if self.stop_callback:
            asyncio.create_task(self.stop_callback())
        else:
            os.kill(os.getpid(), 15)   # SIGTERM

    # ------------------------------------------------------------------
    # /setlive
    # ------------------------------------------------------------------

    async def _cmd_setlive(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        args = context.args or []
        if not args or args[0].lower() != "confirm":
            self._pending_setlive = True
            await self._reply(update, (
                "⚠️ <b>Attention !</b> Tu vas passer en mode <b>LIVE</b>.\n"
                "Tous les trades seront réels et débiteront ton wallet.\n"
                "Pour confirmer: <code>/setlive confirm</code>"
            ))
            return

        if not self._pending_setlive:
            await self._reply(update, "❌ Utilise d'abord <code>/setlive</code> sans argument.")
            return

        # Bascule le flag dry_run en mémoire
        # (redémarrer le bot pour persister via .env)
        settings.__dict__["dry_run"] = False
        self._pending_setlive = False
        logger.warning("[COMMANDS] Switched to LIVE mode via Telegram /setlive confirm")
        await self._reply(update, (
            "🟢 <b>Mode LIVE activé !</b>\n"
            "Les prochains trades seront réels.\n"
            "⚠️ Redémarre le bot avec <code>DRY_RUN=false</code> dans .env pour persister."
        ))

    # ------------------------------------------------------------------
    # /whitelist [adresse]
    # ------------------------------------------------------------------

    async def _cmd_whitelist(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        args = context.args or []
        if not args:
            await self._reply(update, "Usage: <code>/whitelist 0xAdresse...</code>")
            return
        address = args[0].strip().lower()
        with get_db() as db:
            wallet = db.get(TrackedWallet, address)
            if wallet:
                wallet.is_active = True
                setattr(wallet, "whitelisted", True)
                msg = f"✅ <code>{address[:12]}...</code> ajouté à la whitelist."
            else:
                new_w = TrackedWallet(
                    address=address,
                    score=1.0,
                    is_active=True,
                )
                setattr(new_w, "whitelisted", True)
                db.add(new_w)
                msg = f"✅ <code>{address[:12]}...</code> créé et ajouté à la whitelist."
        logger.info(f"[COMMANDS] Whitelisted: {address}")
        await self._reply(update, msg)

    # ------------------------------------------------------------------
    # /blacklist [adresse]
    # ------------------------------------------------------------------

    async def _cmd_blacklist(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        args = context.args or []
        if not args:
            await self._reply(update, "Usage: <code>/blacklist 0xAdresse...</code>")
            return
        address = args[0].strip().lower()
        with get_db() as db:
            wallet = db.get(TrackedWallet, address)
            if wallet:
                wallet.is_active = False
                setattr(wallet, "blacklisted", True)
                msg = f"⛔ <code>{address[:12]}...</code> blacklisté et désactivé."
            else:
                new_w = TrackedWallet(
                    address=address,
                    score=0.0,
                    is_active=False,
                )
                setattr(new_w, "blacklisted", True)
                db.add(new_w)
                msg = f"⛔ <code>{address[:12]}...</code> ajouté à la blacklist."
        logger.info(f"[COMMANDS] Blacklisted: {address}")
        await self._reply(update, msg)
