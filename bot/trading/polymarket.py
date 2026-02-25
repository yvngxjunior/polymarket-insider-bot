import httpx
from typing import Optional
from tenacity import retry, stop_after_attempt, wait_exponential

from bot.config import get_settings
from bot.utils.logger import logger

settings = get_settings()


class PolymarketDataClient:
    """
    Client HTTP async pour les APIs publiques Polymarket.
    - Data API: historique trades, positions, wallets
    - Gamma API: métadonnées des marchés
    """

    def __init__(self):
        self._data_client = httpx.AsyncClient(
            base_url=settings.polymarket_data_host,
            timeout=15.0,
            headers={"User-Agent": "PolyInsiderBot/1.0"},
        )
        self._gamma_client = httpx.AsyncClient(
            base_url=settings.polymarket_gamma_host,
            timeout=15.0,
            headers={"User-Agent": "PolyInsiderBot/1.0"},
        )

    async def close(self):
        await self._data_client.aclose()
        await self._gamma_client.aclose()

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=8))
    async def get_wallet_trades(
        self,
        wallet: str,
        limit: int = 100,
        offset: int = 0
    ) -> list[dict]:
        """Récupère l'historique des trades d'un wallet."""
        try:
            resp = await self._data_client.get(
                "/activity",
                params={"user": wallet, "limit": limit, "offset": offset}
            )
            resp.raise_for_status()
            return resp.json().get("history", [])
        except Exception as e:
            logger.error(f"get_wallet_trades({wallet[:8]}...): {e}")
            return []

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=8))
    async def get_recent_large_trades(
        self,
        min_amount: float,
        limit: int = 50
    ) -> list[dict]:
        """Récupère les gros trades récents sur toute la plateforme."""
        try:
            resp = await self._data_client.get(
                "/activity",
                params={"limit": limit, "sortBy": "usdcSize", "sortOrder": "desc"}
            )
            resp.raise_for_status()
            trades = resp.json().get("history", [])
            return [t for t in trades if float(t.get("usdcSize", 0)) >= min_amount]
        except Exception as e:
            logger.error(f"get_recent_large_trades: {e}")
            return []

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=8))
    async def get_wallet_positions(
        self,
        wallet: str,
        limit: int = 100
    ) -> list[dict]:
        """Récupère les positions ouvertes d'un wallet."""
        try:
            resp = await self._data_client.get(
                "/positions",
                params={"user": wallet, "limit": limit}
            )
            resp.raise_for_status()
            return resp.json().get("positions", [])
        except Exception as e:
            logger.error(f"get_wallet_positions({wallet[:8]}...): {e}")
            return []

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=8))
    async def get_market_info(self, condition_id: str) -> Optional[dict]:
        """Récupère les infos d'un marché via son condition_id."""
        try:
            resp = await self._gamma_client.get(
                "/markets",
                params={"conditionId": condition_id}
            )
            resp.raise_for_status()
            markets = resp.json()
            return markets[0] if markets else None
        except Exception as e:
            logger.error(f"get_market_info({condition_id[:12]}...): {e}")
            return None

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=8))
    async def get_top_traders(
        self,
        limit: int = 200
    ) -> list[dict]:
        """Récupère les meilleurs traders de la plateforme."""
        try:
            resp = await self._data_client.get(
                "/leaderboard",
                params={"limit": limit}
            )
            resp.raise_for_status()
            return resp.json().get("leaderboard", [])
        except Exception as e:
            logger.error(f"get_top_traders: {e}")
            return []
