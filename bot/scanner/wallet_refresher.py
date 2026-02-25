import asyncio
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from bot.scanner.insider import InsiderScanner
from bot.notifications.telegram import TelegramNotifier
from bot.utils.logger import logger


class WalletRefresher:
    """
    Rafraîchit le pool de wallets suivis toutes les heures.
    Détecte les nouveaux insiders et envoie des alertes Telegram.
    """

    def __init__(
        self,
        scanner: InsiderScanner,
        notifier: TelegramNotifier,
        interval_minutes: int = 60,
    ):
        self.scanner = scanner
        self.notifier = notifier
        self.interval_minutes = interval_minutes
        self._known_wallets: set[str] = set()
        self._scheduler = AsyncIOScheduler()

    async def start(self) -> None:
        """Lance le rafraîchissement immédiatement puis toutes les X minutes."""
        await self._run()
        self._scheduler.add_job(
            self._run,
            'interval',
            minutes=self.interval_minutes,
            id='wallet_refresh',
        )
        self._scheduler.start()
        logger.info(f"Wallet refresher scheduled every {self.interval_minutes} min.")

    async def _run(self) -> None:
        try:
            analyses = await self.scanner.refresh_tracked_wallets()
            for a in analyses:
                if a.address not in self._known_wallets:
                    self._known_wallets.add(a.address)
                    await self.notifier.notify_new_insider(
                        wallet=a.address,
                        score=a.score,
                        win_rate=a.win_rate,
                        total_trades=a.total_trades,
                    )
        except Exception as e:
            logger.error(f"WalletRefresher error: {e}")
