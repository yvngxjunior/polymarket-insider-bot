import httpx
import os
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
    
    ALIGNED WITH OFFICIAL DOCS:
    - https://docs.polymarket.com/api-reference/introduction
    - https://gist.github.com/shaunlebron/0dd3338f7dea06b8e9f8724981bb13bf
    """

    def __init__(self):
        # httpx uses 'proxy' (singular), not 'proxies'
        proxy_url = settings.http_proxy if settings.http_proxy else None
        
        if proxy_url:
            logger.info(f"[PolymarketClient] Using HTTP proxy: {proxy_url}")
        
        self._data_client = httpx.AsyncClient(
            base_url=settings.polymarket_data_host,
            timeout=15.0,
            headers={
                "User-Agent": "PolyInsiderBot/1.0",
                "Content-Type": "application/json",
                "Accept": "application/json"
            },
            proxy=proxy_url,  # Correct: 'proxy' not 'proxies'
        )
        self._gamma_client = httpx.AsyncClient(
            base_url=settings.polymarket_gamma_host,
            timeout=15.0,
            headers={
                "User-Agent": "PolyInsiderBot/1.0",
                "Content-Type": "application/json",
                "Accept": "application/json"
            },
            proxy=proxy_url,
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
        """
        GET /activity - Fetches onchain activity for a user.
        Doc: https://gist.github.com/shaunlebron/0dd3338f7dea06b8e9f8724981bb13bf#activity
        """
        resp = await self._data_client.get(
            "/activity",
            params={
                "user": wallet,
                "limit": limit,
                "offset": offset,
                "type": "TRADE",
                "sortBy": "TIMESTAMP",
                "sortDirection": "DESC"
            }
        )
        resp.raise_for_status()
        data = resp.json()
        return data if isinstance(data, list) else []

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=8))
    async def get_recent_large_trades(
        self,
        min_amount: float,
        limit: int = 100
    ) -> list[dict]:
        """
        GET /trades - Fetches trades ordered by timestamp DESC.
        Doc: https://gist.github.com/shaunlebron/0dd3338f7dea06b8e9f8724981bb13bf#trades
        """
        resp = await self._data_client.get(
            "/trades",
            params={
                "limit": limit,
                "takerOnly": "false",
                "filterType": "CASH",
                "filterAmount": int(min_amount),
            }
        )
        resp.raise_for_status()
        data = resp.json()
        trades = data if isinstance(data, list) else []
        
        result = []
        for t in trades:
            result.append({
                "transactionHash": t.get("transactionHash", ""),
                "maker":           t.get("proxyWallet", ""),
                "usdcSize":        float(t.get("size", 0)),
                "conditionId":     t.get("conditionId", ""),
                "asset":           t.get("asset", ""),
                "side":            t.get("side", "BUY"),
                "price":           float(t.get("price", 0)),
                "timestamp":       int(t.get("timestamp", 0)),
                "title":           t.get("title", ""),
            })
        return result

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=8))
    async def get_wallet_positions(
        self,
        wallet: str,
        limit: int = 100
    ) -> list[dict]:
        """
        GET /positions - Fetches current positions for a user.
        Doc: https://gist.github.com/shaunlebron/0dd3338f7dea06b8e9f8724981bb13bf#positions
        """
        resp = await self._data_client.get(
            "/positions",
            params={
                "user": wallet,
                "limit": limit,
                "sizeThreshold": 1.0,
                "sortBy": "CURRENT",
                "sortDirection": "DESC"
            }
        )
        resp.raise_for_status()
        data = resp.json()
        return data if isinstance(data, list) else []

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=8))
    async def get_market_info(self, condition_id: str) -> Optional[dict]:
        """
        GET /markets - Gamma API for market metadata.
        Doc: https://docs.polymarket.com/api-reference/introduction
        """
        resp = await self._gamma_client.get(
            "/markets",
            params={"conditionId": condition_id}
        )
        resp.raise_for_status()
        markets = resp.json()
        if isinstance(markets, list):
            return markets[0] if markets else None
        return markets.get("markets", [None])[0]

    async def get_top_traders(
        self,
        limit: int = 150
    ) -> list[dict]:
        """
        GET /v1/leaderboard - Data API for top traders.
        Max 50 per page, pagination par offset.
        """
        results: list[dict] = []
        page_size = 50
        offset = 0

        while len(results) < limit:
            page = await self._fetch_leaderboard_page(offset=offset, page_size=page_size)
            if not page:
                break
            results.extend(page)
            if len(page) < page_size:
                break
            offset += page_size

        return results[:limit]

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=8))
    async def _fetch_leaderboard_page(self, offset: int, page_size: int) -> list[dict]:
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
        return data if isinstance(data, list) else data.get("leaderboard", data.get("data", []))

    async def get_usdc_balance(self) -> float:
        """
        Calculate USDC capital from positions using GET /value endpoint.
        
        OFFICIAL DOC: https://gist.github.com/shaunlebron/0dd3338f7dea06b8e9f8724981bb13bf#positions-value
        
        This is MORE RELIABLE than CLOB auth for geo-restricted regions.
        Returns total USD value of all open positions.
        """
        try:
            resp = await self._data_client.get(
                "/value",
                params={"user": settings.proxy_wallet}
            )
            resp.raise_for_status()
            data = resp.json()
            
            # Response format: [{"user": "0x...", "value": 123.45}]
            if isinstance(data, list) and len(data) > 0:
                balance = float(data[0].get('value', 0))
                logger.info(f"[PolymarketClient] Fetched positions value: ${balance:.2f}")
                return balance
            
            logger.info("[PolymarketClient] No positions value found")
            return 0.0
            
        except Exception as e:
            logger.error(f"[PolymarketClient] Failed to fetch value: {e}")
            return 0.0
