import httpx
from typing import Optional
from tenacity import retry, stop_after_attempt, wait_exponential

from bot.config import get_settings
from bot.utils.logger import logger

settings = get_settings()


class PolymarketDataClient:
    """
    Client HTTP async pour les APIs publiques Polymarket.
    - Data API : trades, positions, activité, leaderboard  (data-api.polymarket.com)
    - Gamma API: métadonnées des marchés               (gamma-api.polymarket.com)
    Aucun endpoint ne nécessite d'auth pour la lecture publique.

    Champs réels de /trades (cf. docs Polymarket) :
      proxyWallet, side, asset, conditionId, size, price,
      timestamp, title, transactionHash, outcome
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
            data = resp.json()
            if isinstance(data, list):
                return data
            return data.get("history", data.get("data", []))
        except Exception as e:
            logger.error(f"get_wallet_trades({wallet[:8]}...): {e}")
            return []

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=8))
    async def get_recent_large_trades(
        self,
        min_amount: float,
        limit: int = 100
    ) -> list[dict]:
        """
        Récupère les gros trades récents via Data API /trades.
        - Trié par timestamp DESC (plus récent en premier) — garanti par l'API.
        - Filtre CASH côté serveur (filterType + filterAmount) pour n'obtenir
          que les trades >= min_amount USDC sans post-filtrage client.
        - takerOnly=false pour capturer maker ET taker.

        Champ wallet réel : proxyWallet (pas 'maker').
        """
        try:
            resp = await self._data_client.get(
                "/trades",
                params={
                    "limit":        limit,
                    "takerOnly":    "false",
                    "filterType":   "CASH",
                    "filterAmount": int(min_amount),
                }
            )
            resp.raise_for_status()
            data = resp.json()
            trades = data if isinstance(data, list) else data.get("data", data.get("trades", []))
            result = []
            for t in trades:
                size = float(t.get("size", t.get("usdcSize", 0)))
                wallet = t.get("proxyWallet", t.get("maker", ""))
                result.append({
                    "transactionHash": t.get("transactionHash", ""),
                    "maker":           wallet,       # normalisé : toujours 'maker' en interne
                    "usdcSize":        size,
                    "conditionId":     t.get("conditionId", ""),
                    "asset":           t.get("asset", ""),
                    "side":            t.get("side", "BUY"),
                    "price":           float(t.get("price", 0)),
                    "timestamp":       int(t.get("timestamp", 0)),
                    "title":           t.get("title", ""),
                })
            return result
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
            data = resp.json()
            if isinstance(data, list):
                return data
            return data.get("positions", data.get("data", []))
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
            if isinstance(markets, list):
                return markets[0] if markets else None
            return markets.get("markets", [None])[0]
        except Exception as e:
            logger.error(f"get_market_info({condition_id[:12]}...): {e}")
            return None

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=8))
    async def get_top_traders(
        self,
        limit: int = 150
    ) -> list[dict]:
        """
        Récupère les meilleurs traders via /v1/leaderboard.
        Max 50 par page — pagination par offset.
        """
        results: list[dict] = []
        page_size = 50
        offset = 0

        while len(results) < limit:
            try:
                resp = await self._data_client.get(
                    "/v1/leaderboard",
                    params={
                        "limit":    page_size,
                        "offset":   offset,
                        "sortBy":   "VOL",
                        "interval": "ALL",
                    }
                )
                resp.raise_for_status()
                data = resp.json()
                page = data if isinstance(data, list) else data.get("leaderboard", data.get("data", []))
                if not page:
                    break
                results.extend(page)
                if len(page) < page_size:
                    break
                offset += page_size
            except Exception as e:
                logger.error(f"get_top_traders (offset={offset}): {e}")
                break

        return results[:limit]
