import httpx
from typing import Optional
from tenacity import retry, stop_after_attempt, wait_exponential

from bot.config import get_settings
from bot.utils.cache import get_cache_service, CacheTTL
from bot.utils.logger import logger

settings = get_settings()


class PolymarketDataClient:
    """
    Client HTTP async pour les APIs publiques Polymarket.
    - Data API : trades, positions, activité, leaderboard  (data-api.polymarket.com)
    - Gamma API: métadonnées des marchés               (gamma-api.polymarket.com)
    Aucun endpoint ne nécessite d'auth pour la lecture publique.

    FIX BUG-9: get_top_traders() ne porte plus le décorateur @retry global.
    La boucle de pagination interne appelait raise_for_status() sur chaque page.
    Si une page levait une exception, tenacity relançait toute la méthode depuis
    l'offset=0 → résultats dupliqués (ex: 200+200 = 400 entrées pour limit=300).
    Correction: retry appliqué par page via _fetch_leaderboard_page(), et la
    boucle principale dans get_top_traders() accumule sans retry global.
    
    v3.2 (Smart Caching):
    - get_market_info() cache 5min (marchés changent peu)
    - get_wallet_trades() cache 10s (balance fraîcheur vs rate-limits)
    - Réduit latence de 300ms → 5ms pour données cachées
    - Économise ~70% des appels API Polymarket
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
        self.cache = get_cache_service()

    async def close(self):
        await self._data_client.aclose()
        await self._gamma_client.aclose()

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=8))
    async def get_wallet_trades(
        self,
        wallet: str,
        limit: int = 100,
        offset: int = 0,
        use_cache: bool = True,
    ) -> list[dict]:
        """
        Get wallet trades avec cache intelligent.
        
        Args:
            wallet: Wallet address
            limit: Max results
            offset: Pagination offset
            use_cache: Si True, utilise le cache (10s TTL)
        
        Returns:
            List of trades
        """
        # Cache key unique par wallet+limit+offset
        cache_key = f"trades:{wallet}:{limit}:{offset}"
        
        if use_cache:
            cached = await self.cache.get(cache_key)
            if cached is not None:
                logger.debug(f"[CACHE HIT] trades {wallet[:10]}")
                return cached
        
        # Cache miss → fetch API
        resp = await self._data_client.get(
            "/activity",
            params={"user": wallet, "limit": limit, "offset": offset}
        )
        resp.raise_for_status()
        data = resp.json()
        
        if isinstance(data, list):
            trades = data
        else:
            trades = data.get("history", data.get("data", []))
        
        # Cache result (10s TTL — balance fraîcheur vs rate-limits)
        if use_cache:
            await self.cache.set(cache_key, trades, ttl=CacheTTL.WALLET_TRADES)
        
        return trades

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=8))
    async def get_recent_large_trades(
        self,
        min_amount: float,
        limit: int = 100
    ) -> list[dict]:
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
                "maker":           wallet,
                "usdcSize":        size,
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
        resp = await self._data_client.get(
            "/positions",
            params={"user": wallet, "limit": limit}
        )
        resp.raise_for_status()
        data = resp.json()
        if isinstance(data, list):
            return data
        return data.get("positions", data.get("data", []))

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=8))
    async def get_market_info(
        self,
        condition_id: str,
        use_cache: bool = True,
    ) -> Optional[dict]:
        """
        Get market info avec cache intelligent.
        
        Les marchés changent rarement (question, résolution, etc.),
        donc on cache 5 minutes pour réduire drastiquement les appels API.
        
        Args:
            condition_id: Condition ID du marché
            use_cache: Si True, utilise le cache (5min TTL)
        
        Returns:
            Market info dict ou None si introuvable
        """
        cache_key = f"market:{condition_id}"
        
        if use_cache:
            cached = await self.cache.get(cache_key)
            if cached is not None:
                logger.debug(f"[CACHE HIT] market {condition_id[:12]}")
                return cached
        
        # Cache miss → fetch API
        resp = await self._gamma_client.get(
            "/markets",
            params={"conditionId": condition_id}
        )
        resp.raise_for_status()
        markets = resp.json()
        
        if isinstance(markets, list):
            market = markets[0] if markets else None
        else:
            market = markets.get("markets", [None])[0]
        
        # Cache result (5min TTL — marchés stables)
        if use_cache and market:
            await self.cache.set(cache_key, market, ttl=CacheTTL.MARKET_INFO)
        
        return market

    # FIX BUG-9: @retry retiré de get_top_traders().
    # Le retry est désormais appliqué page par page via _fetch_leaderboard_page().
    # La boucle principale ne porte pas de retry global pour éviter les doublons
    # en cas de reprise depuis offset=0 sur une exception tardive.
    async def get_top_traders(
        self,
        limit: int = 150
    ) -> list[dict]:
        """
        Récupère les meilleurs traders via /v1/leaderboard.
        Max 50 par page — pagination par offset.
        Chaque page est fetchée avec retry individuel (pas le tout).
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
        """
        FIX BUG-9: retry appliqué par page, pas sur la boucle entière.
        En cas d'échec sur une page, seule cette page est retentée (3x),
        pas toute la pagination depuis l'offset 0.
        """
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
