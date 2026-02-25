"""
Wallet Scanner — PolyInsider Bot
==================================
Détecte automatiquement de nouveaux wallets insiders potentiels
en combinant deux sources:

  1. Leaderboard Polymarket  — top traders par profit sur 30j
  2. Gros trades récents      — wallets qui font des bets > seuil whale
     sur des marchés peu liquides (signal fort d'information privée)

Pour chaque candidat:
  - Analyse via InsiderScanner.analyze_wallet()
  - Score via WalletScorer (dimensions A/B/C/D)
  - Si qualifié: insère / met à jour TrackedWallet en DB
  - Si déjà connu et désormais non qualifié: désactive

Usage (depuis main.py ou WalletRefresher):
  scanner = WalletScanner(client=client, insider_scanner=insider_scanner)
  new_wallets = await scanner.discover()
  # new_wallets: liste d'adresses nouvellement ajoutées à la DB
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass

from bot.ai.scorer import WalletScorer, WalletTier
from bot.config import get_settings
from bot.database import TrackedWallet, get_db
from bot.scanner.insider import InsiderScanner, WalletAnalysis
from bot.trading.polymarket import PolymarketDataClient
from bot.utils.logger import logger

settings = get_settings()


@dataclass
class DiscoveryResult:
    """Résultat d'un cycle de détection."""
    new_wallets: list[str]          # adresses ajoutées pour la première fois
    updated_wallets: list[str]      # adresses mises à jour (score changé)
    deactivated_wallets: list[str]  # adresses désactivées (plus qualifiées)
    total_candidates: int           # nb de candidats analysés
    total_qualified: int            # nb de wallets qualifiés au final

    def __str__(self) -> str:
        return (
            f"Discovery: +{len(self.new_wallets)} new | "
            f"{len(self.updated_wallets)} updated | "
            f"{len(self.deactivated_wallets)} deactivated | "
            f"{self.total_qualified}/{self.total_candidates} qualified"
        )


class WalletScanner:
    """
    Détecte et qualifie de nouveaux wallets insiders.

    Args:
        client:           PolymarketDataClient
        insider_scanner:  InsiderScanner (analyse individuelle par wallet)
        leaderboard_limit: nombre de top traders à analyser (défaut: 200)
        whale_min_usdc:   seuil de bet pour considérer un wallet "suspect" (défaut: 500)
        max_concurrent:   nombre max d'analyses en parallèle (défaut: 10)
    """

    def __init__(
        self,
        client: PolymarketDataClient,
        insider_scanner: InsiderScanner,
        leaderboard_limit: int = 200,
        whale_min_usdc: float = 500.0,
        max_concurrent: int = 10,
    ) -> None:
        self.client = client
        self.insider = insider_scanner
        self.leaderboard_limit = leaderboard_limit
        self.whale_min_usdc = whale_min_usdc
        self.max_concurrent = max_concurrent
        self._scorer = WalletScorer()
        self._seen: set[str] = set()  # cache pour éviter les doublons intra-cycle

    # ------------------------------------------------------------------
    # Point d'entrée principal
    # ------------------------------------------------------------------

    async def discover(self) -> DiscoveryResult:
        """
        Lance un cycle complet de détection.
        Combine leaderboard + gros trades récents.

        Returns:
            DiscoveryResult avec stats du cycle
        """
        self._seen.clear()
        candidates = await self._collect_candidates()
        logger.info(f"[SCANNER] {len(candidates)} candidates to analyze")

        # Analyse en parallèle avec un semaphore pour limiter la concurrence
        sem = asyncio.Semaphore(self.max_concurrent)

        async def analyze_one(address: str):
            async with sem:
                return await self.insider.analyze_wallet(address)

        results = await asyncio.gather(
            *[analyze_one(addr) for addr in candidates],
            return_exceptions=True,
        )

        return self._process_results(candidates, results)

    # ------------------------------------------------------------------
    # Collecte des candidats
    # ------------------------------------------------------------------

    async def _collect_candidates(self) -> list[str]:
        """Collecte les adresses candidates depuis les deux sources."""
        leaderboard_addrs, whale_addrs = await asyncio.gather(
            self._from_leaderboard(),
            self._from_large_trades(),
            return_exceptions=True,
        )

        addresses: list[str] = []
        for source in (leaderboard_addrs, whale_addrs):
            if isinstance(source, Exception):
                logger.warning(f"[SCANNER] Candidate source error: {source}")
                continue
            for addr in source:
                if addr and addr not in self._seen:
                    self._seen.add(addr)
                    addresses.append(addr)
        return addresses

    async def _from_leaderboard(self) -> list[str]:
        """Top traders du leaderboard Polymarket."""
        try:
            traders = await self.client.get_top_traders(limit=self.leaderboard_limit)
            return [
                t.get("proxyWalletAddress", "")
                for t in traders
                if t.get("proxyWalletAddress")
            ]
        except Exception as e:
            logger.warning(f"[SCANNER] Leaderboard fetch error: {e}")
            return []

    async def _from_large_trades(self) -> list[str]:
        """Wallets ayant récemment fait de gros bets (signal insider potentiel)."""
        try:
            trades = await self.client.get_recent_large_trades(
                min_amount=self.whale_min_usdc, limit=50
            )
            return list({
                t.get("maker", "") or t.get("taker", "")
                for t in trades
                if t.get("maker") or t.get("taker")
            })
        except Exception as e:
            logger.warning(f"[SCANNER] Large trades fetch error: {e}")
            return []

    # ------------------------------------------------------------------
    # Traitement des résultats
    # ------------------------------------------------------------------

    def _process_results(
        self,
        candidates: list[str],
        results: list,
    ) -> DiscoveryResult:
        """Traite les analyses et met à jour la DB."""
        new_wallets: list[str] = []
        updated_wallets: list[str] = []
        deactivated_wallets: list[str] = []
        qualified_count = 0

        with get_db() as db:
            for address, result in zip(candidates, results):
                if isinstance(result, Exception):
                    logger.debug(f"[SCANNER] Analysis failed {address[:8]}: {result}")
                    continue

                analysis: WalletAnalysis = result

                # Calcul du score IA (dimensions A/B/C/D)
                ws = self._scorer.score_wallet(
                    address=address,
                    win_rate=analysis.win_rate_weighted,
                    total_trades=analysis.total_trades,
                    recent_win_rate=analysis.win_rate,
                    avg_bet_usdc=self._estimate_avg_bet(analysis),
                    pnl_stddev=0.0,  # pas disponible ici, conservateur
                )

                existing: TrackedWallet | None = db.get(TrackedWallet, address)

                if not analysis.is_qualified or ws.tier == WalletTier.SKIP:
                    # Désactiver si précédemment actif
                    if existing and existing.is_active:
                        existing.is_active = False
                        deactivated_wallets.append(address)
                        logger.info(
                            f"[SCANNER] ⚠️ Deactivated {address[:10]}... "
                            f"(tier={ws.tier.value} | {analysis.disqualify_reason})"
                        )
                    continue

                qualified_count += 1

                if existing is None:
                    # Nouveau wallet qualifié — insérer en DB
                    wallet = TrackedWallet(
                        address=address,
                        win_rate=analysis.win_rate_weighted,
                        total_trades=analysis.total_trades,
                        total_profit_usd=analysis.total_profit_usd,
                        score=ws.score,
                        is_active=True,
                        is_whale=(ws.tier == WalletTier.ELITE),
                    )
                    db.add(wallet)
                    new_wallets.append(address)
                    logger.info(
                        f"[SCANNER] ✨ New insider [{ws.tier.value}] "
                        f"{address[:10]}... score={ws.score:.2f} "
                        f"WR={analysis.win_rate_weighted:.0%} "
                        f"trades={analysis.total_trades}"
                    )
                else:
                    # Mise à jour du wallet existant
                    prev_score = existing.score or 0.0
                    existing.win_rate = analysis.win_rate_weighted
                    existing.total_trades = analysis.total_trades
                    existing.total_profit_usd = analysis.total_profit_usd
                    existing.score = ws.score
                    existing.is_active = True
                    existing.is_whale = (ws.tier == WalletTier.ELITE)
                    if abs(ws.score - prev_score) > 0.05:
                        updated_wallets.append(address)
                        logger.debug(
                            f"[SCANNER] 🔄 Updated {address[:10]}... "
                            f"score {prev_score:.2f}→{ws.score:.2f}"
                        )

        result = DiscoveryResult(
            new_wallets=new_wallets,
            updated_wallets=updated_wallets,
            deactivated_wallets=deactivated_wallets,
            total_candidates=len(candidates),
            total_qualified=qualified_count,
        )
        logger.info(f"[SCANNER] {result}")
        return result

    @staticmethod
    def _estimate_avg_bet(analysis: WalletAnalysis) -> float:
        """Estime la taille moyenne des bets depuis le profit total et le nb de trades."""
        if analysis.total_trades <= 0:
            return 0.0
        # Heuristique: profit total / nb trades * facteur de levier moyen (5x)
        return abs(analysis.total_profit_usd / analysis.total_trades) * 5
