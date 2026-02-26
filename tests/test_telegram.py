"""
Unit tests — TelegramNotifier
Zéro appels réels: telegram.Bot.send_message est mocké.
Vérifie que chaque méthode notify_*:
  - Appelle bien send_message exactement une fois
  - Envoie du HTML (parse_mode=HTML)
  - Inclut les données clés dans le message
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from bot.notifications.telegram import TelegramNotifier
from bot.database import CopiedTrade, TradeStatus


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def notifier():
    """TelegramNotifier avec Bot mocké (aucun vrai appel réseau)."""
    with patch("bot.notifications.telegram.Bot") as MockBot:
        mock_bot_instance = MagicMock()
        mock_bot_instance.send_message = AsyncMock()
        MockBot.return_value = mock_bot_instance

        with patch("bot.notifications.telegram.get_settings") as mock_settings:
            s = MagicMock()
            s.telegram_bot_token = "test_token"
            s.telegram_chat_id   = "123456"
            s.scan_interval      = 3
            s.max_trade_amount   = 50.0
            s.min_win_rate       = 0.70
            s.whale_threshold    = 500.0
            s.llm_enabled        = False
            s.arb_enabled        = True
            mock_settings.return_value = s

            n = TelegramNotifier()
            n._bot = mock_bot_instance  # injection directe
            yield n, mock_bot_instance


def make_trade(
    status: TradeStatus = TradeStatus.EXECUTED,
    amount: float = 25.0,
    price: float = 0.45,
    side: str = "BUY",
    skip_reason: str = "",
    tx_hash: str = "0xABCDEF",
) -> CopiedTrade:
    trade = MagicMock(spec=CopiedTrade)
    trade.status = status
    trade.amount_usdc = amount
    trade.price = price
    trade.side = side
    trade.skip_reason = skip_reason
    trade.tx_hash = tx_hash
    trade.source_wallet_address = "0xSource001"
    trade.market_question = "Will X happen?"
    return trade


# ---------------------------------------------------------------------------
# Tests notify_trade
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_notify_trade_executed(notifier):
    """notify_trade EXECUTED doit envoyer un message HTML avec ✅."""
    n, bot = notifier
    trade = make_trade(status=TradeStatus.EXECUTED)
    await n.notify_trade(trade, market_question="Will BTC hit 100k?")

    bot.send_message.assert_called_once()
    _, kwargs = bot.send_message.call_args
    text = kwargs["text"]
    assert "✅" in text
    assert "EXECUTED" in text
    assert "BTC" in text
    assert kwargs["parse_mode"] == "HTML"


@pytest.mark.asyncio
async def test_notify_trade_skipped(notifier):
    """notify_trade SKIPPED doit afficher la raison du skip."""
    n, bot = notifier
    trade = make_trade(status=TradeStatus.SKIPPED, skip_reason="LOW_CONVICTION")
    await n.notify_trade(trade)

    _, kwargs = bot.send_message.call_args
    assert "SKIPPED" in kwargs["text"]
    assert "LOW_CONVICTION" in kwargs["text"]


@pytest.mark.asyncio
async def test_notify_trade_dry_run(notifier):
    """notify_trade DRY RUN doit afficher '(DRY RUN)'."""
    n, bot = notifier
    trade = make_trade(status=TradeStatus.EXECUTED, skip_reason="DRY_RUN")
    await n.notify_trade(trade)

    _, kwargs = bot.send_message.call_args
    assert "DRY RUN" in kwargs["text"]


# ---------------------------------------------------------------------------
# Tests notify_whale_event
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_notify_whale_event(notifier):
    """notify_whale_event doit inclure le montant et la direction."""
    n, bot = notifier
    await n.notify_whale_event(
        wallet="0xWhale001AbcDef",
        amount_usdc=1500.0,
        market_question="Will the Fed cut rates?",
        side="BUY",
        price=0.62,
    )

    bot.send_message.assert_called_once()
    _, kwargs = bot.send_message.call_args
    text = kwargs["text"]
    assert "🐋" in text
    assert "1,500" in text
    assert "Fed" in text
    assert "🟢" in text  # BUY = vert


# ---------------------------------------------------------------------------
# Tests notify_new_insider
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_notify_new_insider(notifier):
    """notify_new_insider doit afficher le score et le win rate."""
    n, bot = notifier
    await n.notify_new_insider(
        wallet="0xInsider001XyZ",
        score=0.82,
        win_rate=0.78,
        total_trades=55,
    )

    bot.send_message.assert_called_once()
    _, kwargs = bot.send_message.call_args
    text = kwargs["text"]
    assert "🔍" in text
    assert "55" in text  # total_trades


# ---------------------------------------------------------------------------
# Tests notify_convergence
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_notify_convergence(notifier):
    """notify_convergence doit afficher le nombre d'insiders et la question."""
    n, bot = notifier
    signal = {
        "count": 4,
        "question": "Will Trump win the election?",
        "condition_id": "cond_001",
        "wallets": ["0xA", "0xB", "0xC", "0xD"],
        "side": "BUY",
        "avg_price": 0.55,
    }
    await n.notify_convergence(signal)

    bot.send_message.assert_called_once()
    _, kwargs = bot.send_message.call_args
    text = kwargs["text"]
    assert "🔥" in text
    assert "4" in text
    assert "Trump" in text


# ---------------------------------------------------------------------------
# Tests notify_arbitrage
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_notify_arbitrage(notifier):
    """notify_arbitrage doit afficher le profit % et la stratégie."""
    n, bot = notifier
    opp = MagicMock()
    opp.profit_pct       = 0.04
    opp.direction        = "BUY_YES_POLY_NO_KALSHI"
    opp.poly_question    = "Will the ECB raise rates?"
    opp.poly_yes_price   = 0.42
    opp.kalshi_yes_price = 0.46
    opp.min_capital_usdc = 200.0

    await n.notify_arbitrage(opp)

    bot.send_message.assert_called_once()
    _, kwargs = bot.send_message.call_args
    text = kwargs["text"]
    assert "⚡" in text
    assert "4.0%" in text
    assert "ECB" in text


# ---------------------------------------------------------------------------
# Tests notify_llm_signal
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_notify_llm_signal_buy_yes(notifier):
    """notify_llm_signal BUY_YES doit afficher l'emoji vert et la confiance."""
    n, bot = notifier
    sig = MagicMock()
    sig.recommendation   = "BUY_YES"
    sig.confidence       = 0.84
    sig.question         = "Will Ethereum hit $5k?"
    sig.current_price    = 0.38
    sig.fair_probability = 0.60
    sig.mispricing_pct   = 0.22
    sig.reasoning        = "Strong institutional demand"

    await n.notify_llm_signal(sig)

    bot.send_message.assert_called_once()
    _, kwargs = bot.send_message.call_args
    text = kwargs["text"]
    assert "🤖" in text
    assert "BUY_YES" in text
    assert "84%" in text
    assert "Ethereum" in text
    assert "🟢" in text  # BUY_YES = vert


# ---------------------------------------------------------------------------
# Tests notify_startup
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_notify_startup_dry_run(notifier):
    """notify_startup DRY RUN doit afficher le mode correct."""
    n, bot = notifier
    await n.notify_startup(dry_run=True)

    bot.send_message.assert_called_once()
    _, kwargs = bot.send_message.call_args
    assert "DRY RUN" in kwargs["text"]


@pytest.mark.asyncio
async def test_notify_startup_live(notifier):
    """notify_startup LIVE doit afficher LIVE."""
    n, bot = notifier
    await n.notify_startup(dry_run=False)

    _, kwargs = bot.send_message.call_args
    assert "LIVE" in kwargs["text"]


# ---------------------------------------------------------------------------
# Test résilience: TelegramError ne doit pas crash le bot
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_send_telegram_error_does_not_raise(notifier):
    """Une TelegramError lors de l'envoi ne doit pas lever d'exception."""
    from telegram.error import TelegramError
    n, bot = notifier
    bot.send_message.side_effect = TelegramError("Network error")

    # Ne doit PAS lever d'exception
    await n.send("👋 Test")
