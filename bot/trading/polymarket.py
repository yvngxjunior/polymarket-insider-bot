import httpx
from typing import Optional
from tenacity import retry, stop_after_attempt, wait_exponential

from bot.config import get_settings
from bot.utils.logger import logger

settings = get_settings()


def _safe_float(value, default: float = 0.0) -> float:
    """Robust float conversion for Polymarket numeric fields.

    Official docs specify numeric fields like `size`, `usdcSize`, and `price`
    as numbers, but older payloads or edge-cases can contain null/strings.
    This helper prevents TypeError/ValueError in those cases.[web:268][web:276]
    """
    if value is None:
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


class PolymarketDataClient:
    """Async HTTP client for Polymarket public APIs.

    Covers:
    - Data API  — trades, activity, positions, leaderboard.[web:268][web:274]
    - Gamma API — market metadata and discovery.[web:214]

    Aligned with official docs:
    - Data /trades & /activity limits: limit ≤ 500, offset ≤ 1000.[web:225]
    - Trade schema: `size` (shares), optional `usdcSize` (notional), `price`,
      `asset`, `conditionId`, `proxyWallet`, `transactionHash`, `title`.[web:268][web:276]
    - Activity schema: `size` (tokens), `usdcSize` (USDC.e), `side`, `type`.[web:274]
    """

    def __init__(self):
        proxy_url = settings.http_proxy or None
        if proxy_url:
            logger.info(f"[PolymarketClient] Using HTTP proxy: {proxy_url}")

        common_headers = {
            "User-Agent": "PolyInsiderBot/1.0",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

        self._data_client = httpx.AsyncClient(
            base_url=settings.polymarket_data_host,
            timeout=15.0,
            headers=common_headers,
            proxy=proxy_url,
        )
        self._gamma_client = httpx.AsyncClient(
            base_url=settings.polymarket_gamma_host,
            timeout=15.0,
            headers=common_headers,
            proxy=proxy_url,
        )

    async def close(self) -> None:
        await self._data_client.aclose()
        await self._gamma_client.aclose()

    # ------------------------------------------------------------------
    # Data API — /activity (user on-chain activity)
    # PHASE 1: Complete /activity implementation for all event types
    # ------------------------------------------------------------------

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=8))
    async def get_wallet_trades(
        self,
        wallet: str,
        limit: int = 100,
        offset: int = 0,
    ) -> list[dict]:
        """Fetch recent trade activity for a wallet using /activity.

        Docs: Data-API /activity (Get User On-Chain Activity).[web:274]
        Notes:
        - `limit` is capped at 500, `offset` at 1000 per docs.[web:225]
        - Filtered to type=TRADE and ordered by timestamp DESC.
        """
        # Respect documented bounds
        limit = max(1, min(int(limit), 500))
        offset = max(0, min(int(offset), 1000))

        resp = await self._data_client.get(
            "/activity",
            params={
                "user": wallet,
                "limit": limit,
                "offset": offset,
                "type": "TRADE",
                "sortBy": "TIMESTAMP",
                "sortDirection": "DESC",
            },
        )
        resp.raise_for_status()
        data = resp.json()
        return data if isinstance(data, list) else []

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=8))
    async def get_wallet_activity(
        self,
        wallet: str,
        limit: int = 100,
        offset: int = 0,
        event_type: Optional[str] = None,
    ) -> list[dict]:
        """Fetch complete activity history for a wallet (all event types).
        
        PHASE 1: New method to capture ALL activity types:
        - TRADE (BUY/SELL)
        - REDEEM (claim winnings after resolution)
        - SPLIT (create YES+NO positions from collateral)
        - MERGE (destroy YES+NO to recover collateral)
        
        Args:
            wallet: Wallet address
            limit: Max results (capped at 500)
            offset: Pagination offset (capped at 1000)
            event_type: Filter by specific type (None = all types)
            
        Returns:
            List of activity events with schema:
            {
                "type": "TRADE" | "REDEEM" | "SPLIT" | "MERGE",
                "side": "BUY" | "SELL" (for TRADE only),
                "asset": "0x...",  # token_id
                "conditionId": "0x...",
                "size": float,  # tokens amount
                "usdcSize": float,  # notional in USDC.e
                "price": float,  # 0-1 (for TRADE)
                "timestamp": int,  # unix timestamp
                "title": str,  # market question
            }
        
        Docs: https://docs.polymarket.com/api-reference/core/get-user-activity
        """
        limit = max(1, min(int(limit), 500))
        offset = max(0, min(int(offset), 1000))
        
        params = {
            "user": wallet.lower(),
            "limit": limit,
            "offset": offset,
            "sortBy": "TIMESTAMP",
            "sortDirection": "DESC",
        }
        
        if event_type:
            params["type"] = event_type.upper()
        
        try:
            resp = await self._data_client.get("/activity", params=params)
            resp.raise_for_status()
            data = resp.json()
            return data if isinstance(data, list) else []
        except Exception as e:
            logger.warning(f"[PolymarketClient] get_wallet_activity failed for {wallet[:10]}: {e}")
            return []

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=8))
    async def get_market_activity(
        self,
        condition_id: str,
        limit: int = 500,
        offset: int = 0,
    ) -> list[dict]:
        """Fetch all activity on a specific market.
        
        PHASE 1: Use this to calculate entry timing scores.
        Get all trades/activity on a market to determine when a wallet
        entered relative to total market activity.
        
        Args:
            condition_id: Market condition ID
            limit: Max results (capped at 500)
            offset: Pagination offset (capped at 1000)
            
        Returns:
            List of activity events (all users) on this market
        """
        limit = max(1, min(int(limit), 500))
        offset = max(0, min(int(offset), 1000))
        
        try:
            resp = await self._data_client.get(
                "/activity",
                params={
                    "market": condition_id,
                    "limit": limit,
                    "offset": offset,
                    "sortBy": "TIMESTAMP",
                    "sortDirection": "DESC",
                },
            )
            resp.raise_for_status()
            data = resp.json()
            return data if isinstance(data, list) else []
        except Exception as e:
            logger.warning(f"[PolymarketClient] get_market_activity failed: {e}")
            return []

    # ------------------------------------------------------------------
    # Data API — /trades (global trade feed, used for whales)
    # ------------------------------------------------------------------

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=8))
    async def get_recent_large_trades(
        self,
        min_amount: float,
        limit: int = 100,
    ) -> list[dict]:
        """Fetch large trades across all markets for whale detection.

        Uses Data-API `/trades`, ordered by timestamp DESC.[web:268][web:271]

        Implementation details:
        - Applies `filterType=CASH` + `filterAmount` so server-side filtering is
          done in USDC.e notional.[web:268]
        - Respects new API limits: `limit` ≤ 500.[web:225]
        - Normalizes output fields to a stable schema consumed by WhaleTracker:
          `transactionHash`, `maker`, `usdcSize`, `conditionId`, `asset`,
          `side`, `price`, `timestamp`, `title`.
        - `usdcSize` is derived using the following precedence:
            1. `usdcSize` field if present (Data/Builder trade schema).[web:276][web:282]
            2. `size * price` fallback when only shares + price are provided.[web:268]
        """
        # Respect documented bound
        limit = max(1, min(int(limit), 500))
        # Server-side notional filter in USDC.e
        filter_amount = max(0, int(min_amount))

        resp = await self._data_client.get(
            "/trades",
            params={
                "limit": limit,
                "takerOnly": "false",  # include maker + taker fills
                "filterType": "CASH",
                "filterAmount": filter_amount,
            },
        )
        resp.raise_for_status()
        data = resp.json()
        trades = data if isinstance(data, list) else []

        result: list[dict] = []
        for t in trades:
            raw_size = _safe_float(t.get("size"))        # size in shares[web:268]
            price = _safe_float(t.get("price"))          # price 0–1[web:268]
            usdc_field = t.get("usdcSize")               # optional notional[web:282]
            usdc_size = _safe_float(usdc_field) if usdc_field is not None else 0.0

            if usdc_size <= 0 and raw_size > 0 and price > 0:
                # Fallback: derive notional from shares * price when needed.
                usdc_size = raw_size * price

            result.append(
                {
                    "transactionHash": t.get("transactionHash", ""),
                    "maker": t.get("proxyWallet", ""),
                    "usdcSize": usdc_size,
                    "conditionId": t.get("conditionId", ""),
                    "asset": t.get("asset", ""),
                    "side": t.get("side", "BUY"),
                    "price": price,
                    "timestamp": int(_safe_float(t.get("timestamp"), 0.0)),
                    "title": t.get("title", ""),
                }
            )
        return result

    # ------------------------------------------------------------------
    # Data API — /positions
    # ------------------------------------------------------------------

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=8))
    async def get_wallet_positions(
        self,
        wallet: str,
        limit: int = 100,
    ) -> list[dict]:
        """Fetch current positions for a wallet via /positions.

        Docs: historical community gist for /positions endpoint plus
        polymarket-data SDK examples.[web:268][web:283]
        """
        limit = max(1, min(int(limit), 500))

        resp = await self._data_client.get(
            "/positions",
            params={
                "user": wallet,
                "limit": limit,
                "sizeThreshold": 1.0,
                "sortBy": "CURRENT",
                "sortDirection": "DESC",
            },
        )
        resp.raise_for_status()
        data = resp.json()
        return data if isinstance(data, list) else []

    # ------------------------------------------------------------------
    # Gamma API — /markets (metadata)
    # ------------------------------------------------------------------

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=8))
    async def get_market_info(self, condition_id: str) -> Optional[dict]:
        """Fetch market metadata from Gamma /markets.

        Docs: Gamma API — Events, Markets & Discovery.[web:214][web:223]
        Uses `conditionId` query param to filter by market.
        """
        resp = await self._gamma_client.get(
            "/markets",
            params={"conditionId": condition_id},
        )
        resp.raise_for_status()
        markets = resp.json()
        if isinstance(markets, list):
            return markets[0] if markets else None
        return markets.get("markets", [None])[0]

    # ------------------------------------------------------------------
    # Data API — /v1/leaderboard (top traders)
    # ------------------------------------------------------------------

    async def get_top_traders(self, limit: int = 150) -> list[dict]:
        """Fetch top traders from the leaderboard.

        Endpoint: `/v1/leaderboard` on Data-API host.
        Notes:
        - Underlying API returns up to 50 rows per page; we paginate using
          `offset` until `limit` is reached.
        - Sorted by VOL over interval=ALL to approximate long-term insiders.
        """
        results: list[dict] = []
        page_size = 50
        offset = 0

        limit = max(1, min(int(limit), 500))  # hard cap for sanity

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
                "limit": page_size,
                "offset": offset,
                "sortBy": "VOL",
                "interval": "ALL",
            },
        )
        resp.raise_for_status()
        data = resp.json()
        return data if isinstance(data, list) else data.get("leaderboard", data.get("data", []))

    # ------------------------------------------------------------------
    # Data API — /value (portfolio valuation)
    # ------------------------------------------------------------------

    async def get_usdc_balance(self) -> float:
        """Estimate total USDC.e capital using /value.

        Docs: historical gist for `/value` and polymarket-data SDK usage.[web:268]
        This provides the notional value of all open positions for
        `settings.proxy_wallet`, which the bot uses as capital baseline.
        """
        try:
            resp = await self._data_client.get(
                "/value",
                params={"user": settings.proxy_wallet},
            )
            resp.raise_for_status()
            data = resp.json()

            # Response format: [{"user": "0x...", "value": 123.45}]
            if isinstance(data, list) and data:
                balance = _safe_float(data[0].get("value"), 0.0)
                logger.info(f"[PolymarketClient] Fetched positions value: ${balance:.2f}")
                return balance

            logger.info("[PolymarketClient] No positions value found")
            return 0.0

        except Exception as e:
            logger.error(f"[PolymarketClient] Failed to fetch value: {e}")
            return 0.0
