"""
Health Monitor — PolyInsider Bot v2.4
=======================================
Détecte les crashes silencieux en surveillant l'activité du bot.

Logique:
  - Toutes les HEALTH_CHECK_INTERVAL secondes, vérifie si un trade
    a été exécuté ou évalué dans les derniers SILENCE_THRESHOLD_MIN minutes.
  - Si aucune activité → alerte Telegram "bot silencieux".
  - Un seul ping toutes les ALERT_COOLDOWN_MIN minutes (anti-spam).

Usage:
  monitor = HealthMonitor(notifier=notifier)
  monitor.record_activity()   # appeler dans main_loop à chaque cycle
  await monitor.start()
  ...
  await monitor.stop()
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Optional

from bot.config import get_settings
from bot.notifications.telegram import TelegramNotifier
from bot.utils.logger import logger

settings = get_settings()


class HealthMonitor:
    """
    Surveille l'activité du bot et alerte si silence détecté.

    Args:
        notifier:              TelegramNotifier
        silence_threshold_min: minutes sans activité avant alerte (défaut: 30)
        check_interval_sec:    fréquence de vérification en secondes (défaut: 300 = 5min)
        alert_cooldown_min:    minutes minimum entre deux alertes (défaut: 60)
    """

    def __init__(
        self,
        notifier: TelegramNotifier,
        silence_threshold_min: int = 30,
        check_interval_sec: int = 300,
        alert_cooldown_min: int = 60,
    ) -> None:
        self.notifier = notifier
        self.silence_threshold_min = silence_threshold_min
        self.check_interval_sec = check_interval_sec
        self.alert_cooldown_min = alert_cooldown_min

        self._last_activity: datetime = datetime.now(timezone.utc)
        self._last_alert: Optional[datetime] = None
        self._task: Optional[asyncio.Task] = None
        self._running = False

    # ------------------------------------------------------------------
    # API publique
    # ------------------------------------------------------------------

    def record_activity(self) -> None:
        """Appeler à chaque cycle de main_loop pour signaler que le bot est vivant."""
        self._last_activity = datetime.now(timezone.utc)

    def record_trade(self) -> None:
        """Raccourci: appeler quand un trade est exécuté (réinitialise le timer)."""
        self.record_activity()

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def start(self) -> None:
        self._running = True
        self._task = asyncio.create_task(self._loop(), name="health_monitor")
        logger.info(
            f"[HEALTH] Monitor started — silence threshold={self.silence_threshold_min}min "
            f"check every {self.check_interval_sec}s"
        )

    async def stop(self) -> None:
        self._running = False
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("[HEALTH] Monitor stopped.")

    # ------------------------------------------------------------------
    # Boucle de vérification
    # ------------------------------------------------------------------

    async def _loop(self) -> None:
        while self._running:
            await asyncio.sleep(self.check_interval_sec)
            if not self._running:
                break
            try:
                await self._check()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"[HEALTH] Check error: {e}")

    async def _check(self) -> None:
        now = datetime.now(timezone.utc)
        silent_for = (now - self._last_activity).total_seconds() / 60

        if silent_for < self.silence_threshold_min:
            return

        # Anti-spam: ne pas alerter plus d'une fois par cooldown
        if self._last_alert is not None:
            since_alert = (now - self._last_alert).total_seconds() / 60
            if since_alert < self.alert_cooldown_min:
                return

        self._last_alert = now
        logger.warning(f"[HEALTH] Silence detected: {silent_for:.0f}min without activity")

        await self.notifier.send(
            f"⚠️ <b>Health Alert</b>\n"
            f"────────────────────\n"
            f"🔇 Bot silencieux depuis <b>{silent_for:.0f} min</b>\n"
            f"Aucun trade détecté ou évalué.\n"
            f"<i>Vérifie les logs ou redémarre le bot.</i>\n"
            f"🕒 <code>{now.strftime('%H:%M:%S UTC')}</code>"
        )
