"""Polymarket API client for fetching real-time market data."""
import aiohttp
import asyncio
from typing import Dict, Optional
from bot.utils.logger import logger

class PolymarketAPI:
    """Client for Polymarket CLOB API"""
    
    BASE_URL = "https://clob.polymarket.com"
    
    def __init__(self):
        self.session: Optional[aiohttp.ClientSession] = None
    
    async def _get_session(self) -> aiohttp.ClientSession:
        """Get or create aiohttp session"""
        if self.session is None or self.session.closed:
            self.session = aiohttp.ClientSession()
        return self.session
    
    async def get_market_price(self, market_id: str, token_id: str) -> Optional[float]:
        """Fetch current market price for a specific outcome token.
        
        Args:
            market_id: Polymarket market ID (condition_id)
            token_id: Token ID for YES/NO outcome
            
        Returns:
            Current price as float (0.0-1.0), or None if error
        """
        try:
            session = await self._get_session()
            url = f"{self.BASE_URL}/price"
            params = {
                "token_id": token_id,
                "side": "BUY"
            }
            
            async with session.get(url, params=params, timeout=5) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    price = float(data.get("price", 0.5))
                    return price
                else:
                    logger.warning(f"[PolyAPI] Price fetch failed: {resp.status}")
                    return None
        except Exception as e:
            logger.error(f"[PolyAPI] Error fetching price: {e}")
            return None
    
    async def get_market_orderbook(self, token_id: str) -> Optional[Dict]:
        """Fetch orderbook for a token.
        
        Returns:
            Dict with 'bids' and 'asks' arrays, or None
        """
        try:
            session = await self._get_session()
            url = f"{self.BASE_URL}/book"
            params = {"token_id": token_id}
            
            async with session.get(url, params=params, timeout=5) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    return {
                        "bids": data.get("bids", []),
                        "asks": data.get("asks", [])
                    }
                return None
        except Exception as e:
            logger.error(f"[PolyAPI] Error fetching orderbook: {e}")
            return None
    
    async def close(self):
        """Close aiohttp session"""
        if self.session and not self.session.closed:
            await self.session.close()

# Singleton instance
_polymarket_api: Optional[PolymarketAPI] = None

def get_polymarket_api() -> PolymarketAPI:
    """Get singleton Polymarket API instance"""
    global _polymarket_api
    if _polymarket_api is None:
        _polymarket_api = PolymarketAPI()
    return _polymarket_api
