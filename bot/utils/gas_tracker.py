"""Polygon gas price tracker using Polygonscan API."""
import aiohttp
import asyncio
from typing import Optional
from bot.utils.logger import logger

class GasTracker:
    """Track Polygon gas prices in real-time"""
    
    POLYGONSCAN_API = "https://api.polygonscan.com/api"
    
    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key  # Optional, works without key (limited rate)
        self.session: Optional[aiohttp.ClientSession] = None
        self._cached_gas_price: int = 35
        self._last_update: float = 0
    
    async def _get_session(self) -> aiohttp.ClientSession:
        if self.session is None or self.session.closed:
            self.session = aiohttp.ClientSession()
        return self.session
    
    async def get_gas_price(self) -> int:
        """Fetch current Polygon gas price in gwei.
        
        Returns:
            Gas price in gwei (integer)
        """
        try:
            import time
            now = time.time()
            
            # Cache for 10 seconds
            if now - self._last_update < 10:
                return self._cached_gas_price
            
            session = await self._get_session()
            params = {
                "module": "gastracker",
                "action": "gasoracle"
            }
            if self.api_key:
                params["apikey"] = self.api_key
            
            async with session.get(self.POLYGONSCAN_API, params=params, timeout=5) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    if data.get("status") == "1":
                        result = data.get("result", {})
                        # Polygonscan returns SafeGasPrice (standard speed)
                        gas_price = int(float(result.get("SafeGasPrice", 35)))
                        self._cached_gas_price = gas_price
                        self._last_update = now
                        return gas_price
            
            logger.warning("[GasTracker] Failed to fetch, using cached")
            return self._cached_gas_price
            
        except Exception as e:
            logger.error(f"[GasTracker] Error: {e}")
            return self._cached_gas_price
    
    async def close(self):
        if self.session and not self.session.closed:
            await self.session.close()

# Singleton
_gas_tracker: Optional[GasTracker] = None

def get_gas_tracker() -> GasTracker:
    global _gas_tracker
    if _gas_tracker is None:
        _gas_tracker = GasTracker()
    return _gas_tracker
