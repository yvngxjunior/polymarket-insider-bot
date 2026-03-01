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

FIX REFRESHER-1 — _known_wallets chargé depuis DB au __init__.
  Avant: set() vide → flood Telegram au premier refresh post-restart.
  Après: _load_known_wallets() charge les adresses is_active=True en DB.

FIX REFRESHER-2 — Discovery immédiat si DB vide au démarrage.
  Avant: avec DB vide, discovery attendait le cycle 3 (3h).
  Après: si Refresh #1 trouve 0 wallets actifs, discovery est lancé immédiatement.
  
FIX REFRESHER-3 — Public trigger_refresh() for external triggers
  Permet de forcer un refresh immédiat depuis main loop (ex: après auto-add whale).
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
        wallet_scanner=None,
    ) -> None:
        self.scanner = scanner
        self.notifier = notifier
        self.interval_minutes = interval_minutes
        self.discovery_ratio = discovery_ratio
        self._wallet_scanner = wallet_scanner
        self._refresh_count: int = 0
        self._task: asyncio.Task | None = None
        self._stop_event = asyncio.Event()
        self._refresh_pending = False  # NEW: Flag for external triggers

        # FIX REFRESHER-1: charge les wallets connus depuis la DB au demarrage
        self._known_wallets: set[str] = self._load_known_wallets()

    # ------------------------------------------------------------------
    # FIX REFRESHER-1 — Chargement initial depuis DB
    # ------------------------------------------------------------------

    def _load_known_wallets(self) -> set[str]:
        """
        Charge les adresses de tous les wallets actifs depuis TrackedWallet.
        Retourne un set vide en cas d'erreur DB (premier run, table absente).
        """
        try:
            with get_db() as db:
                addresses = {
                    row.address
                    for row in db.query(TrackedWallet.address)
                    .filter(TrackedWallet.is_active == True)  # noqa: E712
                    .all()
                }
            if addresses:
                logger.info(
                    f"[REFRESHER] Loaded {len(addresses)} known wallet(s) from DB "
                    f"(anti-flood restart protection)"
                )
            return addresses
        except Exception as e:
            logger.warning(f"[REFRESHER] Could not load known wallets from DB: {e}")
            return set()

    def _count_active_wallets(self) -> int:
        """Retourne le nombre de wallets actifs en DB."""
        try:
            with get_db() as db:
                return (
                    db.query(TrackedWallet)
                    .filter(TrackedWallet.is_active == True)  # noqa: E712
                    .count()
                )
        except Exception:
            return 0

    # ------------------------------------------------------------------
    # FIX REFRESHER-3 — Public trigger for external refresh
    # ------------------------------------------------------------------
    
    def trigger_refresh(self) -> None:
        """
        Request an immediate refresh on the next loop iteration.
        Thread-safe, can be called from main loop.
        """
        self._refresh_pending = True
        logger.debug("[REFRESHER] External refresh trigger set")

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
        await self._run_refresh()

        # FIX REFRESHER-2: si DB vide apres le premier refresh,
        # on lance immediatement un discovery plutot d'attendre 3h.
        if self._count_active_wallets() == 0:
            logger.info(
                "[REFRESHER] DB empty after Refresh #1 — "
                "launching immediate discovery..."
            )
            await self._run_discovery()

        while not self._stop_event.is_set():
            try:
                # Check for pending refresh every second
                for _ in range(self.interval_minutes * 60):
                    if self._refresh_pending:
                        self._refresh_pending = False
                        break
                    await asyncio.sleep(1)
                    if self._stop_event.is_set():
                        break
            except asyncio.TimeoutError:
                pass

            if self._stop_event.is_set():
                break

            await self._run_refresh()

            if self._refresh_count > 0 and self._refresh_count % self.discovery_ratio == 0:
                await self._run_discovery()

    # ------------------------------------------------------------------
    # Refresh: recalcule les stats de tous les wallets actifs
    # ------------------------------------------------------------------

    async def _run_refresh(self) -> None:
        self._refresh_count += 1
        logger.info(f"[REFRESHER] Refresh #{self._refresh_count} starting...")

        try:
            analyses = await self.scanner.refresh_tracked_wallets()
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

            for address in result.new_wallets:
                self._known_wallets.add(address)
                try:
                    await self.notifier.notify_new_insider(
                        wallet=address,
                        score=0.0,
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
