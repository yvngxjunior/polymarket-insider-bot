"""Polygon gas price tracker using direct RPC call."""
import aiohttp
import asyncio
import time
from typing import Optional
from bot.utils.logger import logger

class GasTracker:
    """Track Polygon gas prices via RPC"""
    
    def __init__(self, rpc_url: str = "https://polygon-rpc.com"):
        self.rpc_url = rpc_url
        self.session: Optional[aiohttp.ClientSession] = None
        self._cached_gas_price: int = 35
        self._last_update: float = 0
    
    async def _get_session(self) -> aiohttp.ClientSession:
        if self.session is None or self.session.closed:
            self.session = aiohttp.ClientSession()
        return self.session
    
    async def get_gas_price(self) -> int:
        """Fetch current Polygon gas price in gwei via eth_gasPrice RPC call.
        
        Returns:
            Gas price in gwei (integer)
        """
        try:
            now = time.time()
            
            # Cache for 10 seconds
            if now - self._last_update < 10:
                return self._cached_gas_price
            
            session = await self._get_session()
            
            # Direct RPC call: eth_gasPrice
            payload = {
                "jsonrpc": "2.0",
                "method": "eth_gasPrice",
                "params": [],
                "id": 1
            }
            
            async with session.post(
                self.rpc_url, 
                json=payload, 
                timeout=aiohttp.ClientTimeout(total=3)
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    # Response is hex wei, convert to gwei
                    gas_price_wei = int(data.get("result", "0x0"), 16)
                    gas_price_gwei = gas_price_wei // 1_000_000_000
                    
                    self._cached_gas_price = gas_price_gwei
                    self._last_update = now
                    return gas_price_gwei
            
            logger.warning("[GasTracker] Failed to fetch, using cached")
            return self._cached_gas_price
            
        except asyncio.TimeoutError:
            logger.warning("[GasTracker] Timeout")
            return self._cached_gas_price
        except Exception as e:
            logger.error(f"[GasTracker] Error: {e}")
            return self._cached_gas_price
    
    async def close(self):
        if self.session and not self.session.closed:
            await self.session.close()

# Singleton
_gas_tracker: Optional[GasTracker] = None

def get_gas_tracker(rpc_url: str = "https://polygon-rpc.com") -> GasTracker:
    global _gas_tracker
    if _gas_tracker is None:
        _gas_tracker = GasTracker(rpc_url)
    return _gas_tracker
