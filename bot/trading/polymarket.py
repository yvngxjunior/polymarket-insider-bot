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
    Aucun endpoint ne nécessite d'auth pour la lecture publique.

    FIX BUG-9: get_top_traders() ne porte plus le décorateur @retry global.
    La boucle de pagination interne appelait raise_for_status() sur chaque page.
    Si une page levait une exception, tenacity relançait toute la méthode depuis
    l'offset=0 → résultats dupliqués (ex: 200+200 = 400 entrées pour limit=300).
    Correction: retry appliqué par page via _fetch_leaderboard_page(), et la
    boucle principale dans get_top_traders() accumule sans retry global.
    """

    def __init__(self):
        # Proxy config for geo-restricted regions (France, etc.)
        proxy_config = None
        if settings.http_proxy:
            proxy_config = {
                "http://": settings.http_proxy,
                "https://": settings.http_proxy,
            }
            logger.info(f"[PolymarketClient] Using HTTP proxy: {settings.http_proxy}")
        
        self._data_client = httpx.AsyncClient(
            base_url=settings.polymarket_data_host,
            timeout=15.0,
            headers={"User-Agent": "PolyInsiderBot/1.0"},
            proxies=proxy_config,
        )
        self._gamma_client = httpx.AsyncClient(
            base_url=settings.polymarket_gamma_host,
            timeout=15.0,
            headers={"User-Agent": "PolyInsiderBot/1.0"},
            proxies=proxy_config,
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
        resp = await self._data_client.get(
            "/activity",
            params={"user": wallet, "limit": limit, "offset": offset}
        )
        resp.raise_for_status()
        data = resp.json()
        if isinstance(data, list):
            return data
        return data.get("history", data.get("data", []))

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
    async def get_market_info(self, condition_id: str) -> Optional[dict]:
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

    async def get_usdc_balance(self) -> float:
        """
        Get USDC balance using py-clob-client with Builder API credentials.
        
        IMPORTANT: Uses environment variables that py-clob-client auto-detects:
        - POLY_BUILDER_API_KEY
        - POLY_BUILDER_SECRET
        - POLY_BUILDER_PASSPHRASE
        
        For geo-restricted regions (France, etc.), set HTTP_PROXY in .env.
        
        Returns balance as float, or 0.0 if unable to fetch.
        """
        # Set env vars from settings if configured
        if settings.poly_builder_api_key:
            os.environ['POLY_BUILDER_API_KEY'] = settings.poly_builder_api_key
        if settings.poly_builder_secret:
            os.environ['POLY_BUILDER_SECRET'] = settings.poly_builder_secret
        if settings.poly_builder_passphrase:
            os.environ['POLY_BUILDER_PASSPHRASE'] = settings.poly_builder_passphrase
        
        # Set proxy for py-clob-client if configured
        if settings.http_proxy:
            os.environ['HTTP_PROXY'] = settings.http_proxy
            os.environ['HTTPS_PROXY'] = settings.http_proxy
        
        # Check if Builder credentials are set
        if not os.getenv('POLY_BUILDER_API_KEY') or not os.getenv('POLY_BUILDER_SECRET'):
            logger.warning("[PolymarketClient] Builder API credentials not configured")
            logger.info("[PolymarketClient] Set POLY_BUILDER_API_KEY + SECRET + PASSPHRASE in .env")
            return 0.0
        
        try:
            from py_clob_client.client import ClobClient
            
            # ClobClient will auto-detect POLY_BUILDER_* env vars and HTTP_PROXY
            client = ClobClient(
                host=settings.polymarket_host,
                chain_id=settings.chain_id
            )
            
            # Get balance
            balance_response = client.get_balance_allowance()
            
            # Extract USDC balance (in wei, divide by 1e6)
            balance_wei = int(balance_response.get('balance', 0))
            balance_usdc = balance_wei / 1_000_000
            
            logger.info(f"[PolymarketClient] Fetched USDC balance: ${balance_usdc:.2f}")
            return balance_usdc
            
        except ImportError:
            logger.warning("[PolymarketClient] py-clob-client not installed")
            return 0.0
        except Exception as e:
            logger.error(f"[PolymarketClient] Failed to fetch balance: {e}")
            logger.info("[PolymarketClient] If in France/restricted region, configure HTTP_PROXY in .env")
            return 0.0
