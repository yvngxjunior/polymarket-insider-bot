"""
Arbitrage Scanner — inspiré de CarlosIbCu/polymarket-kalshi-btc-arbitrage-bot

Détecte les opportunités d'arbitrage cross-platform entre Polymarket et Kalshi.
Principe: si YES_poly + YES_kalshi < 1.00 → profit garanti sans risque.

Ex: YES @ 0.45 sur Poly + NO @ 0.48 sur Kalshi = coût 0.93 → profit 7%

Activation: ARB_ENABLED=true dans .env
"""
import asyncio
from dataclasses import dataclass
from typing import Optional

import aiohttp

from bot.config import get_settings
from bot.utils.logger import logger

settings = get_settings()


@dataclass
class ArbitrageOpportunity:
    poly_condition_id: str
    poly_question: str
    poly_yes_price: float
    kalshi_ticker: str
    kalshi_yes_price: float
    profit_pct: float          # Ex: 0.07 = 7% de profit garanti
    direction: str             # "BUY_YES_POLY_NO_KALSHI" | "BUY_NO_POLY_YES_KALSHI"
    min_capital_usdc: float    # Capital minimum requis pour exécuter


class ArbitrageScanner:
    """
    Scanner cross-platform Polymarket ↔ Kalshi.
    Surveille les marchés similaires sur les deux plateformes
    et alerte dès qu'un profit risk-free est détectable.
    """

    KALSHI_API = "https://trading-api.kalshi.com/trade-api/v2"
    GAMMA_API = "https://gamma-api.polymarket.com"

    # Mots-clés à ignorer pour le matching titre
    STOP_WORDS = {
        "the", "a", "an", "will", "be", "in", "on", "at", "to",
        "of", "or", "and", "is", "by", "for", "as", "if", "this",
    }

    def __init__(self, min_profit_pct: float = 0.03) -> None:
        self.min_profit_pct = min_profit_pct
        self._session: Optional[aiohttp.ClientSession] = None

    def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=12)
            )
        return self._session

    async def _fetch_kalshi_markets(self) -> list[dict]:
        try:
            async with self._get_session().get(
                f"{self.KALSHI_API}/markets",
                params={"status": "open", "limit": 200},
            ) as resp:
                if resp.status == 200:
                    return (await resp.json()).get("markets", [])
        except Exception as e:
            logger.debug(f"[ARB] Kalshi fetch error: {e}")
        return []

    async def _fetch_poly_markets(self) -> list[dict]:
        try:
            async with self._get_session().get(
                f"{self.GAMMA_API}/markets",
                params={"active": "true", "closed": "false", "limit": 300},
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    return data if isinstance(data, list) else data.get("markets", [])
        except Exception as e:
            logger.debug(f"[ARB] Polymarket fetch error: {e}")
        return []

    def _title_tokens(self, title: str) -> set[str]:
        return {w.lower() for w in title.split() if w.lower() not in self.STOP_WORDS and len(w) > 2}

    def _match_markets(
        self, poly_markets: list[dict], kalshi_markets: list[dict], min_overlap: int = 4
    ) -> list[tuple[dict, dict]]:
        """Matche les marchés cross-platform par similarité de titre."""
        matched = []
        for poly in poly_markets:
            poly_tokens = self._title_tokens(poly.get("question", ""))
            if not poly_tokens:
                continue
            for kalshi in kalshi_markets:
                kalshi_tokens = self._title_tokens(
                    kalshi.get("title", "") + " " + kalshi.get("subtitle", "")
                )
                if len(poly_tokens & kalshi_tokens) >= min_overlap:
                    matched.append((poly, kalshi))
        return matched

    async def scan(self) -> list[ArbitrageOpportunity]:
        """Retourne les opportunités d'arbitrage triées par profit décroissant."""
        if not getattr(settings, "arb_enabled", True):
            return []

        poly_markets, kalshi_markets = await asyncio.gather(
            self._fetch_poly_markets(),
            self._fetch_kalshi_markets(),
            return_exceptions=True,
        )

        if isinstance(poly_markets, Exception) or isinstance(kalshi_markets, Exception):
            logger.warning("[ARB] Failed to fetch markets from one or both platforms")
            return []

        opportunities: list[ArbitrageOpportunity] = []
        matched = self._match_markets(poly_markets, kalshi_markets)
        logger.debug(f"[ARB] {len(matched)} matched pairs from {len(poly_markets)} poly / {len(kalshi_markets)} kalshi")

        for poly, kalshi in matched:
            try:
                tokens = poly.get("tokens", [])
                poly_yes = next(
                    (float(t.get("price", 0)) for t in tokens if t.get("outcome", "").upper() == "YES"),
                    None,
                )
                # Kalshi yes_ask = coût d'achat du YES
                kalshi_yes = float(kalshi.get("yes_ask", 0) or kalshi.get("last_price", 0))

                if not poly_yes or not kalshi_yes or poly_yes <= 0 or kalshi_yes <= 0:
                    continue

                cond_id = poly.get("conditionId", "")
                question = poly.get("question", "")
                ticker = kalshi.get("ticker", "")

                # Direction 1: BUY YES sur Poly + BUY NO sur Kalshi
                cost_1 = poly_yes + (1.0 - kalshi_yes)
                if cost_1 < 1.0 - self.min_profit_pct:
                    opportunities.append(
                        ArbitrageOpportunity(
                            poly_condition_id=cond_id,
                            poly_question=question,
                            poly_yes_price=poly_yes,
                            kalshi_ticker=ticker,
                            kalshi_yes_price=kalshi_yes,
                            profit_pct=round(1.0 - cost_1, 4),
                            direction="BUY_YES_POLY_NO_KALSHI",
                            min_capital_usdc=round(cost_1 * 100, 2),
                        )
                    )

                # Direction 2: BUY NO sur Poly + BUY YES sur Kalshi
                cost_2 = (1.0 - poly_yes) + kalshi_yes
                if cost_2 < 1.0 - self.min_profit_pct:
                    opportunities.append(
                        ArbitrageOpportunity(
                            poly_condition_id=cond_id,
                            poly_question=question,
                            poly_yes_price=poly_yes,
                            kalshi_ticker=ticker,
                            kalshi_yes_price=kalshi_yes,
                            profit_pct=round(1.0 - cost_2, 4),
                            direction="BUY_NO_POLY_YES_KALSHI",
                            min_capital_usdc=round(cost_2 * 100, 2),
                        )
                    )

            except Exception as e:
                logger.debug(f"[ARB] Pair analysis error: {e}")
                continue

        if opportunities:
            logger.info(f"[ARB] {len(opportunities)} arb opportunities found (min profit ≥{self.min_profit_pct:.0%})")

        return sorted(opportunities, key=lambda o: o.profit_pct, reverse=True)

    async def close(self) -> None:
        if self._session and not self._session.closed:
            await self._session.close()
