"""
Wallet Refresher — PolyInsider Bot
=====================================
Tâche de fond qui s'exécute toutes les N minutes.
Effectue deux opérations distinctes:

  1. REFRESH (via InsiderScanner.refresh_tracked_wallets)
     — Recalcule win_rate, score, consecutive_losses pour TOUS les wallets actifs
     — Met à jour TrackedWallet en DB (champ consecutive_losses inclus)
     — Alerte Telegram pour les nouveaux insiders détectés

  2. DISCOVERY (via WalletScanner.discover) — optionnel, toutes les N*discovery_ratio fois
     — Cherche de nouveaux insiders sur le leaderboard + gros trades
     — Alerte Telegram pour chaque nouveau wallet qualifié

La séparation refresh/discovery est importante:
  - refresh: rapide, wallets connus, mis à jour fréquemment (60 min)
  - discovery: lent, 200+ candidats, moins fréquent (tous les 3h par défaut)
"""
from __future__ import annotations

import asyncio

from bot.database import get_db, TrackedWallet
from bot.scanner.insider import InsiderScanner
from bot.notifications.telegram import TelegramNotifier
from bot.utils.logger import logger


class WalletRefresher:
    """
    Background task: refresh + discovery des wallets insiders.

    Args:
        scanner:           InsiderScanner (analyse et refresh des wallets connus)
        notifier:          TelegramNotifier (alertes)
        interval_minutes:  fréquence du refresh en minutes (défaut: 60)
        discovery_ratio:   lance discovery tous les N refreshs (défaut: 3 = toutes les 3h)
        wallet_scanner:    WalletScanner optionnel (injecté ou créé lazy)
    """

    def __init__(
        self,
        scanner: InsiderScanner,
        notifier: TelegramNotifier,
        interval_minutes: int = 60,
        discovery_ratio: int = 3,
        wallet_scanner=None,   # WalletScanner | None — injecté ou créé lazy
    ) -> None:
        self.scanner = scanner
        self.notifier = notifier
        self.interval_minutes = interval_minutes
        self.discovery_ratio = discovery_ratio
        self._wallet_scanner = wallet_scanner
        self._known_wallets: set[str] = set()
        self._refresh_count: int = 0
        self._task: asyncio.Task | None = None
        self._stop_event = asyncio.Event()

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def start(self) -> None:
        """Démarre le background task (exécuté immédiatement puis en boucle)."""
        self._stop_event.clear()
        self._task = asyncio.create_task(self._loop(), name="wallet_refresher")
        logger.info(
            f"[REFRESHER] Started — interval={self.interval_minutes}min "
            f"discovery every {self.discovery_ratio} cycles"
        )

    async def stop(self) -> None:
        """Arrête proprement le background task."""
        self._stop_event.set()
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("[REFRESHER] Stopped.")

    # ------------------------------------------------------------------
    # Boucle principale
    # ------------------------------------------------------------------

    async def _loop(self) -> None:
        """Boucle infinie: refresh + discovery selon le ratio."""
        # Premier run immédiat au démarrage
        await self._run_refresh()

        while not self._stop_event.is_set():
            try:
                await asyncio.wait_for(
                    self._stop_event.wait(),
                    timeout=self.interval_minutes * 60,
                )
            except asyncio.TimeoutError:
                pass

            if self._stop_event.is_set():
                break

            await self._run_refresh()

            # Discovery tous les N refreshs
            if self._refresh_count % self.discovery_ratio == 0:
                await self._run_discovery()

    # ------------------------------------------------------------------
    # Refresh: recalcule les stats de tous les wallets actifs
    # ------------------------------------------------------------------

    async def _run_refresh(self) -> None:
        """
        Refresh complet:
        - Recalcule win_rate, score, consecutive_losses
        - Met à jour la DB (champ consecutive_losses inclus)
        - Alerte pour les nouveaux wallets détectés
        """
        self._refresh_count += 1
        logger.info(f"[REFRESHER] Refresh #{self._refresh_count} starting...")

        try:
            analyses = await self.scanner.refresh_tracked_wallets()

            # Sync consecutive_losses en DB pour chaque wallet refreshé
            await self._sync_consecutive_losses(analyses)

            new_count = 0
            for analysis in analyses:
                if analysis.address not in self._known_wallets:
                    self._known_wallets.add(analysis.address)
                    new_count += 1
                    try:
                        await self.notifier.notify_new_insider(
                            wallet=analysis.address,
                            score=analysis.score,
                            win_rate=analysis.win_rate_weighted,
                            total_trades=analysis.total_trades,
                        )
                    except Exception as e:
                        logger.warning(f"[REFRESHER] Notify error: {e}")

            logger.info(
                f"[REFRESHER] Refresh #{self._refresh_count} done — "
                f"{len(analyses)} wallets | {new_count} new"
            )

        except Exception as e:
            logger.error(f"[REFRESHER] Refresh error: {e}")

    async def _sync_consecutive_losses(self, analyses) -> None:
        """
        Met à jour le champ consecutive_losses de chaque TrackedWallet en DB.
        Ce champ est lu par process_new_trade() dans main.py pour la protection
        contre les séries de pertes (losing streak).
        """
        try:
            with get_db() as db:
                for analysis in analyses:
                    wallet = db.get(TrackedWallet, analysis.address)
                    if wallet is not None:
                        current = getattr(wallet, "consecutive_losses", 0) or 0
                        if current != analysis.consecutive_losses:
                            setattr(wallet, "consecutive_losses", analysis.consecutive_losses)
                            logger.debug(
                                f"[REFRESHER] {analysis.address[:10]}... "
                                f"consecutive_losses: {current}→{analysis.consecutive_losses}"
                            )
        except Exception as e:
            logger.warning(f"[REFRESHER] consecutive_losses sync error: {e}")

    # ------------------------------------------------------------------
    # Discovery: cherche de nouveaux insiders
    # ------------------------------------------------------------------

    async def _run_discovery(self) -> None:
        """Lance un cycle de détection de nouveaux wallets."""
        scanner = self._get_wallet_scanner()
        if scanner is None:
            return

        logger.info("[REFRESHER] Discovery cycle starting...")
        try:
            result = await scanner.discover()

            # Alertes pour les nouveaux wallets trouvés
            for address in result.new_wallets:
                self._known_wallets.add(address)
                try:
                    await self.notifier.notify_new_insider(
                        wallet=address,
                        score=0.0,    # score sera mis à jour au prochain refresh
                        win_rate=0.0,
                        total_trades=0,
                    )
                except Exception as e:
                    logger.warning(f"[REFRESHER] Discovery notify error: {e}")

            logger.info(f"[REFRESHER] Discovery done — {result}")

        except Exception as e:
            logger.error(f"[REFRESHER] Discovery error: {e}")

    def _get_wallet_scanner(self):
        """Retourne le WalletScanner injecté ou None si pas disponible."""
        if self._wallet_scanner is not None:
            return self._wallet_scanner
        # Création lazy si le client est accessible via le scanner
        try:
            from bot.scanner.wallet_scanner import WalletScanner
            client = getattr(self.scanner, "client", None)
            if client:
                self._wallet_scanner = WalletScanner(
                    client=client,
                    insider_scanner=self.scanner,
                )
                return self._wallet_scanner
        except Exception as e:
            logger.debug(f"[REFRESHER] WalletScanner lazy init failed: {e}")
        return None
