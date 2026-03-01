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

    FIX BUG-9: get_top_traders() ne porte plus le décorateur @retry global.
    La boucle de pagination interne appelait raise_for_status() sur chaque page.
    Si une page levait une exception, tenacity relançait toute la méthode depuis
    l'offset=0 → résultats dupliqués (ex: 200+200 = 400 entrées pour limit=300).
    Correction: retry appliqué par page via _fetch_leaderboard_page(), et la
    boucle principale dans get_top_traders() accumule sans retry global.
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

    async def get_usdc_balance(self) -> float:
        """
        Get USDC balance using Polymarket Builder API Key.
        
        Uses API Key + Secret + Passphrase from .env to authenticate.
        Falls back to 0.0 if credentials are not configured.
        
        Returns balance as float.
        """
        # Check if API credentials are configured
        if not settings.polymarket_api_key or not settings.polymarket_api_secret:
            logger.warning("[PolymarketClient] API Key/Secret not configured - returning 0.0")
            logger.info("[PolymarketClient] Add POLYMARKET_API_KEY and POLYMARKET_API_SECRET to .env")
            return 0.0
        
        try:
            # Use httpx to call the balance endpoint with API auth
            import hmac
            import hashlib
            import time
            import base64
            
            timestamp = str(int(time.time()))
            method = "GET"
            path = "/balances"
            
            # Create signature (HMAC-SHA256)
            message = timestamp + method + path
            signature = hmac.new(
                settings.polymarket_api_secret.encode('utf-8'),
                message.encode('utf-8'),
                hashlib.sha256
            ).digest()
            signature_b64 = base64.b64encode(signature).decode('utf-8')
            
            headers = {
                "POLY-API-KEY": settings.polymarket_api_key,
                "POLY-SIGNATURE": signature_b64,
                "POLY-TIMESTAMP": timestamp,
                "POLY-PASSPHRASE": settings.polymarket_api_passphrase or "",
            }
            
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(
                    f"{settings.polymarket_host}{path}",
                    headers=headers
                )
                resp.raise_for_status()
                data = resp.json()
            
            # Extract USDC balance
            balance = 0.0
            if isinstance(data, dict):
                # Check for USDC balance (asset_id or symbol)
                for asset in data.get('balances', []):
                    if asset.get('symbol') == 'USDC' or asset.get('asset') == 'USDC':
                        balance = float(asset.get('balance', 0))
                        break
            
            logger.info(f"[PolymarketClient] Fetched USDC balance: ${balance}")
            return balance
            
        except Exception as e:
            logger.error(f"[PolymarketClient] Failed to fetch balance: {e}")
            return 0.0
