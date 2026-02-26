"""
Commandes Telegram interactives — PolyInsider Bot v2.7
=======================================================
Permet de contrôler le bot depuis Telegram sans toucher au serveur.

Commandes disponibles:
  /status              — état général (mode, wallets actifs, positions ouvertes)
  /pnl                 — P&L du jour + total
  /positions           — liste des positions ouvertes
  /stop                — arrête le bot proprement (envoie signal SIGTERM)
  /setlive             — bascule DRY RUN → LIVE (demande confirmation)
  /whitelist           — ajoute un wallet à la whitelist
  /blacklist           — ajoute un wallet à la blacklist
  /setcapital [montant]— recalcule les tiered multipliers selon ton capital
  /help                — liste des commandes

FIX BUG-4: /status lit risk_manager.portfolio.total_capital au lieu
  d'attributs inexistants _available_capital / _exposed_capital → affichait $0/$0.
FIX BUG-5: /pnl calcule le P&L du jour depuis portfolio.daily_pnl du RiskManager
  au lieu de lire une colonne pnl_usdc inexistante sur CopiedTrade → affichait $0.
FIX BUG-6: /whitelist et /blacklist persistent via settings (get_whitelist/get_blacklist)
  au lieu de setattr volatils non mappés SQLAlchemy → survit aux redémarrages.

FEAT SIZER-2: /setcapital <montant>
  Recalcule les 4 paliers tiered_multipliers selon le capital fourni
  et hot-reload le PositionSizer sans redémarrage.
"""
from __future__ import annotations

import asyncio
import os
import re
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Optional

from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

from bot.config import get_settings
from bot.database import get_db, CopiedTrade, TrackedWallet, TradeStatus
from bot.notifications.telegram import TelegramNotifier
from bot.utils.logger import logger

if TYPE_CHECKING:
    from bot.trading.risk import RiskManager
    from bot.trading.sizing import PositionSizer
    from bot.analytics.performance import PerformanceTracker

settings = get_settings()


def _build_tiered_string(capital: float) -> str:
    """
    Génère automatiquement la chaîne TIERED_MULTIPLIERS à partir du capital.

    Formule:
      Palier 1 : $1          → capital/10   : ×1.0   (petits trades, copie 1:1)
      Palier 2 : capital/10  → capital      : ×0.3   (trades moyens)
      Palier 3 : capital     → capital×10   : ×0.05  (gros trades)
      Palier 4 : capital×10+ → +∞           : ×0.01  (trades massifs ELITE)

    Exemple capital=$300:
      1-30:1.0,30-300:0.3,300-3000:0.05,3000+:0.01

    Exemple capital=$1500:
      1-150:1.0,150-1500:0.3,1500-15000:0.05,15000+:0.01
    """
    t1 = max(1.0, round(capital / 10, 1))
    t2 = round(capital, 1)
    t3 = round(capital * 10, 1)
    return f"1-{t1}:1.0,{t1}-{t2}:0.3,{t2}-{t3}:0.05,{t3}+:0.01"


def _persist_tiered_to_env(tiered_str: str) -> bool:
    """
    Écrit / met à jour TIERED_MULTIPLIERS dans le fichier .env.
    Retourne True si la persistance a réussi.
    """
    env_path = Path(".env")
    if not env_path.exists():
        logger.warning("[COMMANDS] .env introuvable — tiered non persisté")
        return False

    try:
        content = env_path.read_text(encoding="utf-8")
        line = f'TIERED_MULTIPLIERS={tiered_str}'
        if re.search(r'^TIERED_MULTIPLIERS=', content, re.MULTILINE):
            content = re.sub(
                r'^TIERED_MULTIPLIERS=.*$', line, content, flags=re.MULTILINE
            )
        else:
            content = content.rstrip() + f'\n{line}\n'
        env_path.write_text(content, encoding="utf-8")
        return True
    except Exception as e:
        logger.warning(f"[COMMANDS] .env write error: {e}")
        return False


class BotCommandHandler:
    """
    Gère les commandes Telegram entrantes via long-polling.

    Args:
        notifier:            TelegramNotifier (pour envoyer les réponses)
        risk_manager:        RiskManager (positions ouvertes)
        performance_tracker: PerformanceTracker (P&L)
        sizer:               PositionSizer (hot-reload tiered bands)
        stop_callback:       coroutine async appelée par /stop
    """

    def __init__(
        self,
        notifier: TelegramNotifier,
        risk_manager: "RiskManager",
        performance_tracker: "PerformanceTracker",
        sizer: Optional["PositionSizer"] = None,
        stop_callback=None,
    ) -> None:
        self.notifier = notifier
        self.risk_manager = risk_manager
        self.performance_tracker = performance_tracker
        self.sizer = sizer
        self.stop_callback = stop_callback
        self._app: Application | None = None
        self._task: asyncio.Task | None = None
        self._pending_setlive = False

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def start_polling(self) -> None:
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
            ("setcapital", self._cmd_setcapital),
        ]:
            self._app.add_handler(CommandHandler(cmd, fn))

    # ------------------------------------------------------------------
    # Helper
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
            "/status            — État du bot\n"
            "/pnl               — P&amp;L du jour + total\n"
            "/positions         — Positions ouvertes\n"
            "/stop              — Arrêter le bot\n"
            "/setlive           — Passer en mode LIVE\n"
            "/whitelist [addr]  — Forcer le suivi d'un wallet\n"
            "/blacklist [addr]  — Blacklister un wallet\n"
            "/setcapital [montant] — Ajuster les paliers de sizing\n"
            "  Ex: <code>/setcapital 500</code>\n"
        ))

    # ------------------------------------------------------------------
    # /status — FIX BUG-4
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

        portfolio    = self.risk_manager.portfolio
        total_cap    = portfolio.total_capital
        n_open       = len(self.risk_manager._open_positions)
        avg_pos_size = settings.max_trade_amount
        exposed_est  = min(n_open * avg_pos_size, total_cap)
        available    = max(0.0, total_cap - exposed_est)

        # Affiche les paliers actifs si tiered configuré
        tiered_line = ""
        if settings.tiered_multipliers:
            tiered_line = f"\n📐 Tiered: <code>{settings.tiered_multipliers[:50]}</code>"

        await self._reply(update, (
            f"🤖 <b>Bot Status</b>\n"
            f"────────────────────\n"
            f"Mode: <b>{mode}</b>\n"
            f"👥 Wallets actifs: <b>{active_wallets}</b>\n"
            f"📂 Positions ouvertes: <b>{open_positions}</b> ({n_open} en mémoire)\n"
            f"💰 Capital total: <b>${total_cap:,.2f}</b>\n"
            f"📊 Capital dispo (est.): <b>${available:,.2f}</b>\n"
            f"📉 Exposé (est.): <b>${exposed_est:,.2f}</b>\n"
            f"📈 Drawdown: <b>{portfolio.drawdown_pct:.1%}</b>\n"
            f"⏱ Scan: <b>{settings.scan_interval}s</b>"
            f"{tiered_line}\n"
        ))

    # ------------------------------------------------------------------
    # /pnl — FIX BUG-5
    # ------------------------------------------------------------------

    async def _cmd_pnl(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        try:
            stats = await self.performance_tracker.get_summary()
        except Exception:
            stats = {}

        total_pnl    = stats.get("total_pnl_usdc", 0.0)
        win_rate     = stats.get("win_rate", 0.0)
        total_trades = stats.get("total_trades", 0)
        pnl_emoji    = "🟢" if total_pnl >= 0 else "🔴"

        today_pnl   = self.risk_manager.portfolio.daily_pnl
        today_emoji = "🟢" if today_pnl >= 0 else "🔴"

        await self._reply(update, (
            f"💹 <b>P&amp;L Report</b>\n"
            f"────────────────────\n"
            f"{today_emoji} Aujourd'hui: <b>{today_pnl:+.2f} USDC</b>\n"
            f"{pnl_emoji} Total cumulé: <b>{total_pnl:+.2f} USDC</b>\n"
            f"🎯 Win rate: <b>{win_rate:.1%}</b>\n"
            f"🔄 Trades: <b>{total_trades}</b>\n"
            f"💰 Capital: <b>${self.risk_manager.portfolio.total_capital:,.2f}</b>\n"
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
            os.kill(os.getpid(), 15)  # SIGTERM

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

        settings.__dict__["dry_run"] = False
        self._pending_setlive = False
        logger.warning("[COMMANDS] Switched to LIVE mode via Telegram /setlive confirm")
        await self._reply(update, (
            "🟢 <b>Mode LIVE activé !</b>\n"
            "Les prochains trades seront réels.\n"
            "⚠️ Redémarre le bot avec <code>DRY_RUN=false</code> dans .env pour persister."
        ))

    # ------------------------------------------------------------------
    # /whitelist — FIX BUG-6
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
                wallet.score = max(float(wallet.score or 0.0), 0.65)
                msg = (
                    f"✅ <code>{address[:12]}...</code> activé (score préservé).\n"
                    f"<i>Pour une whitelist permanente, ajoute dans .env:\n"
                    f"WALLET_WHITELIST={address}</i>"
                )
            else:
                new_w = TrackedWallet(
                    address=address,
                    score=0.80,
                    is_active=True,
                )
                db.add(new_w)
                msg = (
                    f"✅ <code>{address[:12]}...</code> créé et activé (score=0.80).\n"
                    f"<i>Pour une whitelist permanente, ajoute dans .env:\n"
                    f"WALLET_WHITELIST={address}</i>"
                )
        logger.info(f"[COMMANDS] Whitelisted (session): {address}")
        await self._reply(update, msg)

    # ------------------------------------------------------------------
    # /blacklist — FIX BUG-6
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
                wallet.score = 0.0
                msg = (
                    f"⛔ <code>{address[:12]}...</code> désactivé (score=0).\n"
                    f"<i>Pour une blacklist permanente, ajoute dans .env:\n"
                    f"WALLET_BLACKLIST={address}</i>"
                )
            else:
                new_w = TrackedWallet(
                    address=address,
                    score=0.0,
                    is_active=False,
                )
                db.add(new_w)
                msg = (
                    f"⛔ <code>{address[:12]}...</code> blacklisté (score=0).\n"
                    f"<i>Pour une blacklist permanente, ajoute dans .env:\n"
                    f"WALLET_BLACKLIST={address}</i>"
                )
        logger.info(f"[COMMANDS] Blacklisted (session): {address}")
        await self._reply(update, msg)

    # ------------------------------------------------------------------
    # /setcapital — FEAT SIZER-2
    # ------------------------------------------------------------------

    async def _cmd_setcapital(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """
        /setcapital [montant]

        Sans argument : affiche la config tiered active.
        Avec montant  : recalcule les 4 paliers et hot-reload le sizer.

        Formule automatique:
          Palier 1 : $1          → capital/10   ×1.0
          Palier 2 : capital/10  → capital      ×0.3
          Palier 3 : capital     → capital×10   ×0.05
          Palier 4 : capital×10+ → +∞           ×0.01

        Exemple /setcapital 300:
          1-30:1.0,30-300:0.3,300-3000:0.05,3000+:0.01
        """
        args = context.args or []

        # --- Sans argument : afficher la config active ---
        if not args:
            current = settings.tiered_multipliers
            if current:
                await self._reply(update, (
                    f"📐 <b>Tiered Multipliers actifs</b>\n"
                    f"────────────────────\n"
                    f"<code>{current}</code>\n\n"
                    f"Pour changer: <code>/setcapital 500</code>"
                ))
            else:
                await self._reply(update, (
                    "📐 Aucun tiered multiplier configuré (Kelly pur).\n"
                    "Pour en configurer un: <code>/setcapital 500</code>"
                ))
            return

        # --- Validation du montant ---
        try:
            capital = float(args[0].replace(",", ".").replace("$", ""))
            if capital < 10:
                await self._reply(update, "❌ Capital minimum: $10")
                return
            if capital > 1_000_000:
                await self._reply(update, "❌ Capital maximum: $1,000,000")
                return
        except ValueError:
            await self._reply(update, "❌ Montant invalide. Exemple: <code>/setcapital 500</code>")
            return

        # --- Génération des paliers ---
        tiered_str = _build_tiered_string(capital)
        t1 = max(1.0, round(capital / 10, 1))
        t2 = round(capital, 1)
        t3 = round(capital * 10, 1)

        # --- Hot-reload settings (session) ---
        settings.__dict__["tiered_multipliers"] = tiered_str

        # --- Hot-reload PositionSizer (si injecté) ---
        sizer_reloaded = False
        if self.sizer is not None:
            try:
                from bot.trading.sizing import _parse_tiered_multipliers
                self.sizer._tiered_bands = _parse_tiered_multipliers(tiered_str)
                self.sizer.update_capital(capital)
                sizer_reloaded = True
            except Exception as e:
                logger.warning(f"[COMMANDS] Sizer hot-reload error: {e}")

        # --- Persistance dans .env ---
        persisted = _persist_tiered_to_env(tiered_str)
        persist_note = (
            "✅ Sauvegardé dans <code>.env</code>" if persisted
            else "⚠️ Non sauvegardé (ajoute manuellement dans <code>.env</code>)"
        )

        logger.info(
            f"[COMMANDS] /setcapital ${capital:.0f} → {tiered_str} "
            f"(sizer={'reloaded' if sizer_reloaded else 'not injected'})"
        )

        await self._reply(update, (
            f"💰 <b>Capital mis à jour : ${capital:,.0f}</b>\n"
            f"────────────────────\n"
            f"📐 <b>Nouveaux paliers :</b>\n"
            f"  $1 – ${t1:.0f}     → ×1.0  <i>(trades ≤ capital/10)</i>\n"
            f"  ${t1:.0f} – ${t2:.0f}  → ×0.3  <i>(trades moyens)</i>\n"
            f"  ${t2:.0f} – ${t3:.0f} → ×0.05 <i>(gros trades)</i>\n"
            f"  ${t3:.0f}+          → ×0.01 <i>(trades ELITE)</i>\n"
            f"────────────────────\n"
            f"🔁 Sizer hot-reloadé: <b>{'✅' if sizer_reloaded else '⚠️ non injecté'}</b>\n"
            f"{persist_note}\n"
        ))
