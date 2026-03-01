"""
Wallet Refresher — PolyInsider Bot
=====================================
Tâche de fond qui s'exécute toutes les N minutes.
Effectue deux opérations distinctes:

  1. REFRESH (via InsiderScanner.refresh_tracked_wallets)
     — Recalcule win_rate, score, consecutive_losses pour TOUS les wallets actifs
     — Met à jour TrackedWallet en DB (champ consecutive_losses inclus)
     — Alerte Telegram pour les nouveaux insiders détectés
     PHASE 2: + ActivityAnalyzer pour entry_timing_score et win rate précis

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

PHASE 2 — ActivityAnalyzer integration
  - Calculate accurate win rates using REDEEM events
  - Enrich whale scores with WhaleExitMonitor conviction scores
  - Log enhanced analytics during refresh
"""
from __future__ import annotations

import asyncio

from bot.database import get_db, TrackedWallet
from bot.scanner.insider import InsiderScanner
from bot.scanner.activity_analyzer import ActivityAnalyzer  # PHASE 2
from bot.scanner.whale_exit_monitor import WhaleExitMonitor  # PHASE 2
from bot.notifications.telegram import TelegramNotifier
from bot.utils.logger import logger


class WalletRefresher:
    """
    Background task: refresh + discovery des wallets insiders.
    PHASE 2: Enhanced with ActivityAnalyzer for better scoring.

    Args:
        scanner:           InsiderScanner (analyse et refresh des wallets connus)
        notifier:          TelegramNotifier (alertes)
        interval_minutes:  fréquence du refresh en minutes (défaut: 60)
        discovery_ratio:   lance discovery tous les N refreshs (défaut: 3 = toutes les 3h)
        wallet_scanner:    WalletScanner optionnel (injecté ou créé lazy)
        activity_analyzer: ActivityAnalyzer optionnel (PHASE 2)
        whale_exit_monitor: WhaleExitMonitor optionnel (PHASE 2)
    """

    def __init__(
        self,
        scanner: InsiderScanner,
        notifier: TelegramNotifier,
        interval_minutes: int = 60,
        discovery_ratio: int = 3,
        wallet_scanner=None,
        activity_analyzer: ActivityAnalyzer | None = None,  # PHASE 2
        whale_exit_monitor: WhaleExitMonitor | None = None,  # PHASE 2
    ) -> None:
        self.scanner = scanner
        self.notifier = notifier
        self.interval_minutes = interval_minutes
        self.discovery_ratio = discovery_ratio
        self._wallet_scanner = wallet_scanner
        self._activity_analyzer = activity_analyzer  # PHASE 2
        self._whale_exit_monitor = whale_exit_monitor  # PHASE 2
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
            f"discovery every {self.discovery_ratio} cycles | "
            f"ActivityAnalyzer: {'ON' if self._activity_analyzer else 'OFF'}"
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
    # PHASE 2: Enhanced refresh with ActivityAnalyzer
    # ------------------------------------------------------------------

    async def _run_refresh(self) -> None:
        self._refresh_count += 1
        logger.info(f"[REFRESHER] Refresh #{self._refresh_count} starting...")

        try:
            analyses = await self.scanner.refresh_tracked_wallets()
            await self._sync_consecutive_losses(analyses)

            # PHASE 2: Enrich scores with ActivityAnalyzer
            if self._activity_analyzer:
                await self._enrich_with_activity_analysis(analyses)
            
            # PHASE 2: Enrich whale scores with exit patterns
            if self._whale_exit_monitor:
                await self._enrich_whale_conviction_scores()

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

    async def _enrich_with_activity_analysis(self, analyses) -> None:
        """PHASE 2: Calculate accurate win rates and update DB.
        
        For each wallet, calculate:
        - Accurate win rate using REDEEM events
        - Average hold time
        - Total PnL estimate
        
        Updates TrackedWallet with better metrics.
        """
        try:
            logger.info("[REFRESHER] Running ActivityAnalyzer enrichment...")
            
            enrichment_count = 0
            for analysis in analyses:
                try:
                    # Calculate accurate win rate
                    win_rate_result = await self._activity_analyzer.calculate_accurate_win_rate(
                        wallet=analysis.address,
                        lookback_days=30,
                    )
                    
                    if win_rate_result and win_rate_result.total_markets >= 5:
                        # Update DB with accurate metrics
                        with get_db() as db:
                            wallet = db.get(TrackedWallet, analysis.address)
                            if wallet:
                                # Only update if significantly different
                                old_wr = wallet.win_rate or 0.5
                                new_wr = win_rate_result.win_rate
                                
                                if abs(new_wr - old_wr) > 0.05:  # > 5% difference
                                    wallet.win_rate = new_wr
                                    wallet.total_trades = win_rate_result.total_markets
                                    
                                    logger.info(
                                        f"[REFRESHER] 📊 {analysis.address[:10]}... | "
                                        f"Win Rate: {old_wr:.1%} → {new_wr:.1%} (accurate via REDEEM) | "
                                        f"Markets: {win_rate_result.winning_markets}W-{win_rate_result.losing_markets}L-{win_rate_result.ongoing_markets}O | "
                                        f"Avg Hold: {win_rate_result.avg_hold_hours:.1f}h"
                                    )
                                    enrichment_count += 1
                
                except Exception as e:
                    logger.debug(f"[REFRESHER] ActivityAnalyzer failed for {analysis.address[:10]}: {e}")
            
            if enrichment_count > 0:
                logger.info(f"[REFRESHER] ActivityAnalyzer enriched {enrichment_count} wallets")
        
        except Exception as e:
            logger.warning(f"[REFRESHER] ActivityAnalyzer enrichment error: {e}")

    async def _enrich_whale_conviction_scores(self) -> None:
        """PHASE 2: Update whale scores based on exit behavior patterns.
        
        Uses WhaleExitMonitor.enrich_whale_scores() to:
        - Analyze REDEEM vs SELL patterns
        - Calculate conviction scores
        - Apply score adjustments (+0.05 for high conviction, -0.10 for low)
        """
        try:
            logger.info("[REFRESHER] Running whale conviction score enrichment...")
            
            adjustments = await self._whale_exit_monitor.enrich_whale_scores()
            
            if adjustments:
                with get_db() as db:
                    for wallet_addr, adjustment in adjustments.items():
                        wallet = db.get(TrackedWallet, wallet_addr)
                        if wallet:
                            old_score = wallet.score or 0.70
                            new_score = max(0.0, min(1.0, old_score + adjustment))
                            wallet.score = new_score
                            
                            logger.info(
                                f"[REFRESHER] 🐳 {wallet_addr[:10]}... | "
                                f"Score: {old_score:.2f} → {new_score:.2f} "
                                f"({adjustment:+.2f} conviction adjustment)"
                            )
                
                logger.info(f"[REFRESHER] Whale conviction enriched {len(adjustments)} whales")
        
        except Exception as e:
            logger.warning(f"[REFRESHER] Whale conviction enrichment error: {e}")

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
