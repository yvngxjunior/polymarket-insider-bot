from telegram import Bot
from telegram.constants import ParseMode
from telegram.error import TelegramError

from bot.config import get_settings
from bot.database import CopiedTrade, TradeStatus
from bot.utils.helpers import get_score_label
from bot.utils.logger import logger

settings = get_settings()


class TelegramNotifier:
    """
    Envoie des alertes Telegram formatées pour chaque événement du bot.
    Utilise MarkdownV2 pour un rendu propre.
    """

    def __init__(self):
        self._bot = Bot(token=settings.telegram_bot_token)
        self._chat_id = settings.telegram_chat_id

    async def send(self, message: str) -> None:
        """Envoie un message brut."""
        try:
            await self._bot.send_message(
                chat_id=self._chat_id,
                text=message,
                parse_mode=ParseMode.HTML,
                disable_web_page_preview=True,
            )
        except TelegramError as e:
            logger.error(f"Telegram send failed: {e}")

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

    async def notify_trade(
        self,
        trade: CopiedTrade,
        market_question: str = "",
    ) -> None:
        status_map = {
            TradeStatus.EXECUTED: ("✅", "EXECUTED"),
            TradeStatus.SKIPPED: ("⛔", "SKIPPED"),
            TradeStatus.FAILED: ("❌", "FAILED"),
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
            + (f"⛔ Reason: {trade.skip_reason}\n" if trade.skip_reason and trade.skip_reason != "DRY_RUN" else "")
            + (f"🔗 TX: <code>{trade.tx_hash}</code>\n" if trade.tx_hash else "")
        )
        await self.send(msg)

    async def notify_startup(self, dry_run: bool) -> None:
        mode = "🟡 DRY RUN" if dry_run else "🟢 LIVE"
        msg = (
            f"🤖 <b>PolyInsider Bot Started</b>\n"
            f"────────────────────\n"
            f"Mode: <b>{mode}</b>\n"
            f"Scan interval: <b>{settings.scan_interval}s</b>\n"
            f"Max trade: <b>${settings.max_trade_amount}</b>\n"
            f"Min win rate: <b>{settings.min_win_rate:.0%}</b>\n"
            f"Whale threshold: <b>${settings.whale_threshold:,.0f}</b>\n"
        )
        await self.send(msg)
