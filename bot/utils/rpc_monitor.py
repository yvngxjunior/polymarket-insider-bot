"""RPC latency monitor for Polygon providers (Infura, Alchemy, etc.)."""
import aiohttp
import asyncio
import time
from typing import Optional
from bot.utils.logger import logger

class RPCMonitor:
    """Monitor RPC provider latency"""
    
    def __init__(self, rpc_url: str):
        self.rpc_url = rpc_url
        self.session: Optional[aiohttp.ClientSession] = None
        self._cached_latency: int = 50
        self._last_check: float = 0
    
    async def _get_session(self) -> aiohttp.ClientSession:
        if self.session is None or self.session.closed:
            self.session = aiohttp.ClientSession()
        return self.session
    
    async def ping(self) -> int:
        """Ping RPC provider and measure latency.
        
        Returns:
            Latency in milliseconds
        """
        try:
            now = time.time()
            
            # Cache for 5 seconds
            if now - self._last_check < 5:
                return self._cached_latency
            
            session = await self._get_session()
            
            # Simple eth_blockNumber call
            payload = {
                "jsonrpc": "2.0",
                "method": "eth_blockNumber",
                "params": [],
                "id": 1
            }
            
            start = time.time()
            async with session.post(
                self.rpc_url, 
                json=payload, 
                timeout=aiohttp.ClientTimeout(total=3)
            ) as resp:
                await resp.json()
                latency_ms = int((time.time() - start) * 1000)
                
                self._cached_latency = latency_ms
                self._last_check = now
                return latency_ms
        
        except asyncio.TimeoutError:
            logger.warning("[RPCMonitor] Timeout (>3s)")
            return 3000
        except Exception as e:
            logger.error(f"[RPCMonitor] Error: {e}")
            return self._cached_latency
    
    async def close(self):
        if self.session and not self.session.closed:
            await self.session.close()

# Singleton
_rpc_monitor: Optional[RPCMonitor] = None

def get_rpc_monitor(rpc_url: str = "https://polygon-rpc.com") -> RPCMonitor:
    """Get singleton RPC monitor.
    
    Args:
        rpc_url: Polygon RPC endpoint (defaults to public node)
    """
    global _rpc_monitor
    if _rpc_monitor is None:
        _rpc_monitor = RPCMonitor(rpc_url)
    return _rpc_monitor
