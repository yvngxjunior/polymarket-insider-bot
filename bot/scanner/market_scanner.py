"""
Market Scanner — inspiré de ImMike/polymarket-arbitrage

Scan asynchrone haute performance de 10 000+ marchés Polymarket.
Utilise asyncio + semaphore pour ne pas flood l'API (max N requêtes simultanées).

Détecte:
  - Arbitrage interne: YES + NO < 1.00 (profit risk-free sur même plateforme)
  - Marchés sous-liquides mais valorisés (potentiel de mouvement)
"""
import asyncio
from dataclasses import dataclass
from typing import Optional

import aiohttp

from bot.config import get_settings
from bot.utils.logger import logger

settings = get_settings()

PAGE_SIZE = 500


@dataclass
class MarketSignal:
    condition_id: str
    question: str
    yes_price: float
    no_price: float
    spread: float           # yes + no - 1.0 (négatif = arb interne)
    volume_24h: float
    signal_type: str        # "INTERNAL_ARB" | "LOW_LIQUIDITY" | "MISPRICED"


class MarketScanner:
    """
    Scanner haute performance — couvre l'ensemble du catalogue Polymarket.
    Chaque page de 500 marchés est fetch en parallèle avec un semaphore
    pour limiter la concurrence à max_concurrent requêtes simultanées.
    """

    GAMMA = "https://gamma-api.polymarket.com"

    def __init__(self, max_concurrent: int = 8) -> None:
        self._sem = asyncio.Semaphore(max_concurrent)
        self._session: Optional[aiohttp.ClientSession] = None

    def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=15)
            )
        return self._session

    async def _fetch_page(self, offset: int) -> list[dict]:
        async with self._sem:
            try:
                async with self._get_session().get(
                    f"{self.GAMMA}/markets",
                    params={
                        "active": "true",
                        "closed": "false",
                        "limit": PAGE_SIZE,
                        "offset": offset,
                    },
                ) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        return data if isinstance(data, list) else []
            except Exception as e:
                logger.debug(f"[SCANNER] Page offset={offset} error: {e}")
            return []

    def _analyze(self, market: dict) -> Optional[MarketSignal]:
        """Analyse un marché individuel et retourne un signal si anomalie détectée."""
        try:
            tokens = market.get("tokens", [])
            yes_price = next(
                (float(t.get("price", 0)) for t in tokens if t.get("outcome", "").upper() == "YES"),
                None,
            )
            no_price = next(
                (float(t.get("price", 0)) for t in tokens if t.get("outcome", "").upper() == "NO"),
                None,
            )

            if yes_price is None or no_price is None or yes_price <= 0 or no_price <= 0:
                return None

            spread = yes_price + no_price - 1.0
            volume = float(market.get("volume24hr", 0) or 0)
            cond_id = market.get("conditionId", "")
            question = market.get("question", "")

            # Arb interne: YES + NO < 0.98 (profit garanti après fees)
            if spread < -0.02:
                return MarketSignal(
                    condition_id=cond_id,
                    question=question,
                    yes_price=yes_price,
                    no_price=no_price,
                    spread=spread,
                    volume_24h=volume,
                    signal_type="INTERNAL_ARB",
                )

            # Marché peu liquide mais prix centré (potentiel de mouvement)
            if volume < 500 and 0.10 <= yes_price <= 0.90 and 0.10 <= no_price <= 0.90:
                return MarketSignal(
                    condition_id=cond_id,
                    question=question,
                    yes_price=yes_price,
                    no_price=no_price,
                    spread=spread,
                    volume_24h=volume,
                    signal_type="LOW_LIQUIDITY",
                )
        except Exception:
            pass
        return None

    async def scan_all(self, max_markets: int = 5000) -> list[MarketSignal]:
        """Lance le scan complet et retourne tous les signaux détectés."""
        if not getattr(settings, "market_scan_enabled", True):
            return []

        offsets = list(range(0, max_markets, PAGE_SIZE))
        pages = await asyncio.gather(
            *[self._fetch_page(o) for o in offsets],
            return_exceptions=True,
        )

        signals: list[MarketSignal] = []
        total = 0

        for page in pages:
            if isinstance(page, Exception) or not page:
                continue
            total += len(page)
            for market in page:
                sig = self._analyze(market)
                if sig:
                    signals.append(sig)

        arb_count = sum(1 for s in signals if s.signal_type == "INTERNAL_ARB")
        logger.info(
            f"[SCANNER] {total:,} markets scanned → "
            f"{len(signals)} signals ({arb_count} internal arb)"
        )
        return sorted(signals, key=lambda s: abs(s.spread), reverse=True)

    async def close(self) -> None:
        if self._session and not self._session.closed:
            await self._session.close()
