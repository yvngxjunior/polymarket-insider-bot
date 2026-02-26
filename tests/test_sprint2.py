"""
Unit tests — Sprint 2
Couvre: HealthMonitor, config whitelist/blacklist, BotCommandHandler (logique métier uniquement).
Zéro appels Telegram réels.
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from bot.notifications.health import HealthMonitor
from bot.notifications.telegram import TelegramNotifier


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_notifier() -> TelegramNotifier:
    n = MagicMock(spec=TelegramNotifier)
    n.send = AsyncMock()
    return n


# ===========================================================================
# HealthMonitor
# ===========================================================================

@pytest.mark.asyncio
async def test_health_no_alert_when_active():
    """Pas d'alerte si l'activité est récente."""
    notifier = make_notifier()
    monitor = HealthMonitor(
        notifier=notifier,
        silence_threshold_min=30,
        check_interval_sec=1,
    )
    monitor.record_activity()   # activité juste maintenant
    await monitor._check()
    notifier.send.assert_not_called()


@pytest.mark.asyncio
async def test_health_alert_when_silent():
    """Alerte envoyée si silence > threshold."""
    notifier = make_notifier()
    monitor = HealthMonitor(
        notifier=notifier,
        silence_threshold_min=30,
        check_interval_sec=1,
    )
    # Simule 40 minutes de silence
    monitor._last_activity = datetime.now(timezone.utc) - timedelta(minutes=40)
    await monitor._check()
    notifier.send.assert_called_once()
    assert "silencieux" in notifier.send.call_args[0][0].lower()


@pytest.mark.asyncio
async def test_health_alert_cooldown():
    """Deux check consécutifs ne doivent envoyer qu'une seule alerte (cooldown)."""
    notifier = make_notifier()
    monitor = HealthMonitor(
        notifier=notifier,
        silence_threshold_min=30,
        check_interval_sec=1,
        alert_cooldown_min=60,
    )
    monitor._last_activity = datetime.now(timezone.utc) - timedelta(minutes=40)
    await monitor._check()   # → alerte
    await monitor._check()   # → cooldown, pas de 2e alerte
    assert notifier.send.call_count == 1


@pytest.mark.asyncio
async def test_health_record_trade_resets_timer():
    """record_trade() doit réinitialiser le timer."""
    notifier = make_notifier()
    monitor = HealthMonitor(notifier=notifier, silence_threshold_min=30)
    monitor._last_activity = datetime.now(timezone.utc) - timedelta(minutes=40)
    monitor.record_trade()   # reset
    await monitor._check()   # ne devrait PAS alerter
    notifier.send.assert_not_called()


@pytest.mark.asyncio
async def test_health_start_stop():
    """start/stop ne doit pas lever d'exception."""
    notifier = make_notifier()
    monitor = HealthMonitor(
        notifier=notifier,
        silence_threshold_min=30,
        check_interval_sec=999,
    )
    await monitor.start()
    await asyncio.sleep(0.02)
    await monitor.stop()
    assert monitor._task is None or monitor._task.done()


# ===========================================================================
# Config — whitelist / blacklist
# ===========================================================================

def test_config_whitelist_parsing():
    """get_whitelist() doit parser le CSV en minuscules."""
    from bot.config import Settings
    s = Settings.model_construct(
        wallet_whitelist="0xAAAA, 0xBBBB ,0xCCCC",
        wallet_blacklist="",
        # champs obligatoires avec valeurs fictives
        private_key="0x01",
        proxy_wallet="0x01",
        telegram_bot_token="tok",
        telegram_chat_id="123",
        database_url="sqlite:///test.db",
    )
    wl = s.get_whitelist()
    assert "0xaaaa" in wl
    assert "0xbbbb" in wl
    assert "0xcccc" in wl
    assert len(wl) == 3


def test_config_blacklist_parsing():
    """get_blacklist() doit parser le CSV."""
    from bot.config import Settings
    s = Settings.model_construct(
        wallet_whitelist="",
        wallet_blacklist="0xDEAD,0xBEEF",
        private_key="0x01",
        proxy_wallet="0x01",
        telegram_bot_token="tok",
        telegram_chat_id="123",
        database_url="sqlite:///test.db",
    )
    bl = s.get_blacklist()
    assert "0xdead" in bl
    assert "0xbeef" in bl


def test_config_empty_lists():
    """Listes vides → sets vides."""
    from bot.config import Settings
    s = Settings.model_construct(
        wallet_whitelist="",
        wallet_blacklist="",
        private_key="0x01",
        proxy_wallet="0x01",
        telegram_bot_token="tok",
        telegram_chat_id="123",
        database_url="sqlite:///test.db",
    )
    assert s.get_whitelist() == set()
    assert s.get_blacklist() == set()
