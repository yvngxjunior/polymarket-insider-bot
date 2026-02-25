from __future__ import annotations

from typing import TYPE_CHECKING

from telegram import Bot
from telegram.constants import ParseMode
from telegram.error import TelegramError

from bot.config import get_settings
from bot.database import CopiedTrade, TradeStatus
from bot.utils.helpers import get_score_label
from bot.utils.logger import logger

if TYPE_CHECKING:
    from bot.scanner.arbitrage import ArbitrageOpportunity
    from bot.ai.llm_agent import LLMSignal

settings = get_settings()


class TelegramNotifier:
    """
    Envoie des alertes Telegram HTML pour chaque événement du bot.
    Méthodes disponibles:
      - notify_trade()         → trade copié (EXECUTED / SKIPPED / FAILED)
      - notify_whale_event()   → grosse transaction détectée
      - notify_new_insider()   → nouveau wallet insider scoré
      - notify_convergence()   → plusieurs insiders sur même marché
      - notify_arbitrage()     → opportunité arb Poly↔Kalshi
      - notify_llm_signal()    → recommandation GPT-4o-mini
      - notify_startup()       → démarrage du bot
    """

    def __init__(self) -> None:
        self._bot = Bot(token=settings.telegram_bot_token)
        self._chat_id = settings.telegram_chat_id

    # ------------------------------------------------------------------
    # Envoi brut
    # ------------------------------------------------------------------
    async def send(self, message: str) -> None:
        try:
            await self._bot.send_message(
                chat_id=self._chat_id,
                text=message,
                parse_mode=ParseMode.HTML,
                disable_web_page_preview=True,
            )
        except TelegramError as e:
            logger.error(f"Telegram send failed: {e}")

    # ------------------------------------------------------------------
    # Trade copié
    # ------------------------------------------------------------------
    async def notify_trade(
        self,
        trade: CopiedTrade,
        market_question: str = "",
    ) -> None:
        status_map = {
            TradeStatus.EXECUTED: ("✅", "EXECUTED"),
            TradeStatus.SKIPPED:  ("⛔", "SKIPPED"),
            TradeStatus.FAILED:   ("❌", "FAILED"),
        }
        emoji, label = status_map.get(trade.status, ("❓", "UNKNOWN"))
        dry = " <i>(DRY RUN)</i>" if trade.skip_reason == "DRY_RUN" else ""
        question = (market_question or trade.market_question or "Unknown Market")[:80]

        msg = (
            f"{emoji} <b>Trade {label}</b>{dry}\n"
            f"────────────────────\n"
            f"📊 Market: <i>{question}</i>\n"
            f"💰 Amount: <b>${trade.amount_usdc:.2f} USDC</b> {trade.side}\n"
            f"🎯 Price: <b>{trade.price:.3f}</b>\n"
            f"👤 Source: <code>{(trade.source_wallet_address or '')[:10]}...</code>\n"
            + (f"⛔ Reason: {trade.skip_reason}\n"
               if trade.skip_reason and trade.skip_reason != "DRY_RUN" else "")
            + (f"🔗 TX: <code>{trade.tx_hash}</code>\n" if trade.tx_hash else "")
        )
        await self.send(msg)

    # ------------------------------------------------------------------
    # Whale alert
    # ------------------------------------------------------------------
    async def notify_whale_event(
        self,
        wallet: str,
        amount_usdc: float,
        market_question: str,
        side: str,
        price: float,
    ) -> None:
        side_emoji = "🟢" if side.upper() == "BUY" else "🔴"
        msg = (
            f"🐋 <b>Whale Alert!</b>\n"
            f"────────────────────\n"
            f"💼 Wallet: <code>{wallet[:10]}...{wallet[-6:]}</code>\n"
            f"💰 Amount: <b>${amount_usdc:,.0f} USDC</b>\n"
            f"📊 Market: <i>{market_question[:80] or 'Unknown'}</i>\n"
            f"{side_emoji} Side: <b>{side}</b> @ {price:.3f}\n"
        )
        await self.send(msg)

    # ------------------------------------------------------------------
    # Nouveau wallet insider détecté
    # ------------------------------------------------------------------
    async def notify_new_insider(
        self,
        wallet: str,
        score: float,
        win_rate: float,
        total_trades: int,
    ) -> None:
        label = get_score_label(score)
        msg = (
            f"🔍 <b>New Insider Detected</b>\n"
            f"────────────────────\n"
            f"💼 Wallet: <code>{wallet[:10]}...{wallet[-6:]}</code>\n"
            f"🎯 Score: <b>{score:.1f}/100</b> {label}\n"
            f"📈 Win Rate: <b>{win_rate:.0%}</b>\n"
            f"🔄 Trades: <b>{total_trades}</b>\n"
            f"<i>Now tracking this wallet for copy trades.</i>"
        )
        await self.send(msg)

    # ------------------------------------------------------------------
    # Convergence — plusieurs insiders sur le même marché
    # ------------------------------------------------------------------
    async def notify_convergence(self, signal: dict) -> None:
        """
        signal keys: count, question, condition_id, wallets (list), side, avg_price
        """
        count    = signal.get("count", 0)
        question = signal.get("question", "Unknown")[:80]
        side     = signal.get("side", "BUY").upper()
        price    = signal.get("avg_price", 0.0)
        wallets  = signal.get("wallets", [])

        side_emoji = "🟢" if side == "BUY" else "🔴"
        msg = (
            f"🔥 <b>Insider Convergence!</b>\n"
            f"────────────────────\n"
            f"📊 Market: <i>{question}</i>\n"
            f"👥 Insiders: <b>{count} wallets</b> on same side\n"
            f"{side_emoji} Side: <b>{side}</b> @ avg {price:.3f}\n"
            + (f"💼 Wallets:\n" + "\n".join(
                f"  • <code>{w[:10]}...</code>"
                for w in wallets[:5]
            ) if wallets else "")
        )
        await self.send(msg)

    # ------------------------------------------------------------------
    # Arbitrage cross-platform Polymarket ↔ Kalshi
    # ------------------------------------------------------------------
    async def notify_arbitrage(self, opp: ArbitrageOpportunity) -> None:
        direction_label = {
            "BUY_YES_POLY_NO_KALSHI":  "BUY YES on Poly + NO on Kalshi",
            "BUY_NO_POLY_YES_KALSHI":  "BUY NO on Poly + YES on Kalshi",
        }.get(opp.direction, opp.direction)

        msg = (
            f"⚡ <b>Arbitrage Opportunity!</b>\n"
            f"────────────────────\n"
            f"📊 Market: <i>{opp.poly_question[:70]}</i>\n"
            f"💰 Profit: <b>+{opp.profit_pct:.1%}</b> risk-free\n"
            f"📋 Strategy: {direction_label}\n"
            f"🏛 Poly YES: <b>{opp.poly_yes_price:.3f}</b>\n"
            f"🏛 Kalshi YES: <b>{opp.kalshi_yes_price:.3f}</b>\n"
            f"💵 Min capital: <b>${opp.min_capital_usdc:.0f} USDC</b>\n"
        )
        await self.send(msg)

    # ------------------------------------------------------------------
    # Signal LLM (GPT-4o-mini)
    # ------------------------------------------------------------------
    async def notify_llm_signal(self, sig: LLMSignal) -> None:
        rec_emoji = {
            "BUY_YES": "🟢",
            "BUY_NO":  "🔴",
            "HOLD":    "⚪",
        }.get(sig.recommendation, "❓")

        msg = (
            f"🤖 <b>AI Signal</b> (GPT-4o-mini)\n"
            f"────────────────────\n"
            f"📊 Market: <i>{sig.question[:70]}</i>\n"
            f"{rec_emoji} Recommendation: <b>{sig.recommendation}</b>\n"
            f"🎯 Confidence: <b>{sig.confidence:.0%}</b>\n"
            f"📈 Current: {sig.current_price:.3f} → Fair: <b>{sig.fair_probability:.3f}</b>\n"
            f"📊 Mispricing: <b>{sig.mispricing_pct:.1%}</b>\n"
            f"💬 <i>{sig.reasoning}</i>\n"
        )
        await self.send(msg)

    # ------------------------------------------------------------------
    # Démarrage du bot
    # ------------------------------------------------------------------
    async def notify_startup(self, dry_run: bool) -> None:
        mode = "🟡 DRY RUN" if dry_run else "🟢 LIVE"
        msg = (
            f"🤖 <b>PolyInsider Bot v2.1 Started</b>\n"
            f"────────────────────\n"
            f"Mode: <b>{mode}</b>\n"
            f"Scan interval: <b>{settings.scan_interval}s</b>\n"
            f"Max trade: <b>${settings.max_trade_amount}</b>\n"
            f"Min win rate: <b>{settings.min_win_rate:.0%}</b>\n"
            f"Whale threshold: <b>${settings.whale_threshold:,.0f}</b>\n"
            f"LLM: <b>{'enabled 🧠' if settings.llm_enabled else 'disabled'}</b>\n"
            f"Arb: <b>{'enabled ⚡' if settings.arb_enabled else 'disabled'}</b>\n"
        )
        await self.send(msg)
