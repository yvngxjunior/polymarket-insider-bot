"""Rate Limiter with exponential backoff for API calls"""
import asyncio
import time
from typing import Dict, Optional
from collections import deque
from functools import wraps

from bot.utils.logger import logger


class RateLimiter:
    """Token bucket rate limiter with exponential backoff"""
    
    def __init__(
        self,
        calls_per_second: float = 10.0,
        burst_size: int = 20,
        backoff_base: float = 2.0,
        max_backoff: float = 60.0,
    ):
        self.calls_per_second = calls_per_second
        self.burst_size = burst_size
        self.backoff_base = backoff_base
        self.max_backoff = max_backoff
        
        # Token bucket
        self.tokens = burst_size
        self.last_refill = time.time()
        self.lock = asyncio.Lock()
        
        # Backoff tracking per endpoint
        self.backoff_delays: Dict[str, float] = {}
        self.recent_calls: deque = deque(maxlen=100)
        
    async def acquire(self, endpoint: str = "default") -> None:
        """Acquire permission to make API call"""
        async with self.lock:
            # Refill tokens
            now = time.time()
            elapsed = now - self.last_refill
            tokens_to_add = elapsed * self.calls_per_second
            
            self.tokens = min(self.burst_size, self.tokens + tokens_to_add)
            self.last_refill = now
            
            # Wait if no tokens available
            if self.tokens < 1:
                wait_time = (1 - self.tokens) / self.calls_per_second
                logger.debug(f"[RATE_LIMIT] Waiting {wait_time:.2f}s for token")
                await asyncio.sleep(wait_time)
                self.tokens = 1
                
            # Apply exponential backoff if endpoint is throttled
            backoff = self.backoff_delays.get(endpoint, 0)
            if backoff > 0:
                logger.warning(
                    f"[RATE_LIMIT] Backoff {backoff:.1f}s for {endpoint}"
                )
                await asyncio.sleep(backoff)
                
            # Consume token
            self.tokens -= 1
            self.recent_calls.append((endpoint, now))
            
    def record_success(self, endpoint: str) -> None:
        """Record successful call - reset backoff"""
        if endpoint in self.backoff_delays:
            del self.backoff_delays[endpoint]
            logger.debug(f"[RATE_LIMIT] Backoff reset for {endpoint}")
            
    def record_rate_limit(self, endpoint: str, retry_after: Optional[float] = None) -> None:
        """Record rate limit hit - increase backoff"""
        current_backoff = self.backoff_delays.get(endpoint, 0)
        
        if retry_after:
            # Use server-provided retry-after
            new_backoff = retry_after
        elif current_backoff == 0:
            # First backoff
            new_backoff = 1.0
        else:
            # Exponential increase
            new_backoff = min(
                current_backoff * self.backoff_base,
                self.max_backoff,
            )
            
        self.backoff_delays[endpoint] = new_backoff
        logger.warning(
            f"[RATE_LIMIT] Hit for {endpoint} - backoff now {new_backoff:.1f}s"
        )
        
    def get_stats(self) -> Dict[str, any]:
        """Get rate limiter statistics"""
        now = time.time()
        recent_window = [c for c in self.recent_calls if now - c[1] < 60]
        
        return {
            "tokens_available": round(self.tokens, 2),
            "calls_last_minute": len(recent_window),
            "avg_calls_per_second": len(recent_window) / 60.0,
            "endpoints_throttled": len(self.backoff_delays),
            "active_backoffs": dict(self.backoff_delays),
        }


# Global rate limiter instance
_global_limiter: Optional[RateLimiter] = None

def get_rate_limiter() -> RateLimiter:
    """Get or create global rate limiter"""
    global _global_limiter
    if _global_limiter is None:
        _global_limiter = RateLimiter(
            calls_per_second=10.0,  # Conservative default
            burst_size=20,
        )
    return _global_limiter


def rate_limited(endpoint: str = "default"):
    """Decorator for rate-limited async functions"""
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            limiter = get_rate_limiter()
            
            # Acquire rate limit token
            await limiter.acquire(endpoint)
            
            try:
                result = await func(*args, **kwargs)
                limiter.record_success(endpoint)
                return result
            except Exception as e:
                # Check if rate limit error
                error_msg = str(e).lower()
                if "429" in error_msg or "rate limit" in error_msg:
                    # Extract retry-after if available
                    retry_after = None
                    if hasattr(e, "response") and hasattr(e.response, "headers"):
                        retry_after = e.response.headers.get("Retry-After")
                        if retry_after:
                            try:
                                retry_after = float(retry_after)
                            except ValueError:
                                retry_after = None
                                
                    limiter.record_rate_limit(endpoint, retry_after)
                raise
                
        return wrapper
    return decorator


# Example usage:
# @rate_limited("polymarket_trades")
# async def fetch_trades(wallet: str):
#     # API call here
#     pass
