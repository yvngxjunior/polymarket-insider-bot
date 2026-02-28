"""
Rate Limiter v1.0
==================
Gestion des limites API Polymarket avec exponential backoff.
Prévient les 429 errors et optimise les requêtes.

Features:
- Token bucket algorithm
- Exponential backoff sur 429
- Stats tracking (requests/min)
- Thread-safe avec asyncio.Lock
"""
import asyncio
import time
from typing import Optional
from dataclasses import dataclass
from collections import deque

from bot.utils.logger import logger


@dataclass
class RateLimitStats:
    """Stats rate limiting."""
    total_requests: int
    throttled_requests: int
    avg_requests_per_min: float
    last_throttle_time: Optional[float]


class RateLimiter:
    """
    Rate limiter avec token bucket + exponential backoff.
    
    Usage:
        limiter = RateLimiter(max_requests=60, window_seconds=60)
        await limiter.acquire()  # Bloque si rate limit atteint
        # ... faire requête API ...
    """
    
    def __init__(
        self,
        max_requests: int = 60,
        window_seconds: float = 60.0,
        burst_size: int = 10,
    ):
        """
        Args:
            max_requests: Nombre max requêtes par fenêtre
            window_seconds: Taille fenêtre en secondes
            burst_size: Taille max du burst (tokens dispo instantanément)
        """
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self.burst_size = min(burst_size, max_requests)
        
        # Token bucket
        self.tokens = float(burst_size)
        self.last_refill = time.time()
        self.refill_rate = max_requests / window_seconds  # tokens/sec
        
        # Stats
        self.request_times = deque(maxlen=1000)
        self.total_requests = 0
        self.throttled_count = 0
        self.last_throttle_time: Optional[float] = None
        
        # Thread safety
        self._lock = asyncio.Lock()
        
        # Exponential backoff state
        self.backoff_delay = 1.0  # seconds
        self.max_backoff = 60.0
        self.backoff_multiplier = 2.0
    
    def _refill_tokens(self) -> None:
        """Refill tokens bucket selon le temps écoulé."""
        now = time.time()
        elapsed = now - self.last_refill
        
        # Ajoute tokens proportionnels au temps écoulé
        new_tokens = elapsed * self.refill_rate
        self.tokens = min(self.tokens + new_tokens, self.burst_size)
        self.last_refill = now
    
    async def acquire(self, cost: float = 1.0) -> None:
        """
        Acquiert permission pour faire une requête.
        Bloque si rate limit atteint.
        
        Args:
            cost: Coût en tokens (1.0 = 1 requête standard)
        """
        async with self._lock:
            self._refill_tokens()
            
            # Si pas assez de tokens, attend
            while self.tokens < cost:
                wait_time = (cost - self.tokens) / self.refill_rate
                self.throttled_count += 1
                self.last_throttle_time = time.time()
                
                logger.debug(
                    f"[RATE_LIMIT] Throttling for {wait_time:.2f}s "
                    f"(tokens={self.tokens:.1f}/{self.burst_size})"
                )
                
                await asyncio.sleep(wait_time)
                self._refill_tokens()
            
            # Consomme tokens
            self.tokens -= cost
            self.total_requests += 1
            self.request_times.append(time.time())
    
    async def handle_429_response(self, retry_after: Optional[int] = None) -> None:
        """
        Gère une réponse 429 (rate limit API).
        Applique exponential backoff.
        
        Args:
            retry_after: Header Retry-After de la réponse (secondes)
        """
        if retry_after:
            delay = min(retry_after, self.max_backoff)
        else:
            delay = min(self.backoff_delay, self.max_backoff)
            self.backoff_delay *= self.backoff_multiplier
        
        logger.warning(
            f"[RATE_LIMIT] 429 received — backing off for {delay:.1f}s "
            f"(backoff_delay={self.backoff_delay:.1f}s)"
        )
        
        await asyncio.sleep(delay)
        
        # Reset tokens à 0 pour forcer attente
        async with self._lock:
            self.tokens = 0.0
            self.last_refill = time.time()
    
    def reset_backoff(self) -> None:
        """Reset exponential backoff après succès."""
        self.backoff_delay = 1.0
    
    def get_stats(self) -> RateLimitStats:
        """Retourne stats rate limiting."""
        now = time.time()
        
        # Calcule requests/min sur dernière minute
        recent_requests = [
            t for t in self.request_times
            if now - t <= 60.0
        ]
        rpm = len(recent_requests)
        
        return RateLimitStats(
            total_requests=self.total_requests,
            throttled_requests=self.throttled_count,
            avg_requests_per_min=rpm,
            last_throttle_time=self.last_throttle_time,
        )
    
    async def wait_if_needed(self, cost: float = 1.0) -> bool:
        """
        Vérifie si rate limit atteint et attend si nécessaire.
        
        Returns:
            True si a dû attendre, False sinon
        """
        async with self._lock:
            self._refill_tokens()
            
            if self.tokens < cost:
                wait_time = (cost - self.tokens) / self.refill_rate
                await asyncio.sleep(wait_time)
                self._refill_tokens()
                return True
            
            return False


# Instance globale pour Polymarket API
polymarket_limiter = RateLimiter(
    max_requests=60,   # 60 req/min
    window_seconds=60.0,
    burst_size=10,
)


async def rate_limited_request(func, *args, max_retries: int = 3, **kwargs):
    """
    Wrapper pour requête API avec rate limiting automatique.
    
    Usage:
        result = await rate_limited_request(client.get_market, market_id)
    
    Args:
        func: Fonction async à appeler
        max_retries: Nombre max de retries sur 429
    
    Returns:
        Résultat de func(*args, **kwargs)
    """
    for attempt in range(max_retries):
        # Acquire rate limit token
        await polymarket_limiter.acquire()
        
        try:
            result = await func(*args, **kwargs)
            polymarket_limiter.reset_backoff()
            return result
        
        except Exception as e:
            error_str = str(e).lower()
            
            # Détecte 429 error
            if "429" in error_str or "rate limit" in error_str:
                if attempt < max_retries - 1:
                    await polymarket_limiter.handle_429_response()
                    logger.info(
                        f"[RATE_LIMIT] Retry {attempt + 1}/{max_retries} after 429"
                    )
                    continue
                else:
                    logger.error("[RATE_LIMIT] Max retries reached on 429")
                    raise
            else:
                # Autre erreur, propage
                raise
    
    raise RuntimeError(f"Rate limited request failed after {max_retries} retries")


if __name__ == "__main__":
    # Test rate limiter
    async def test():
        limiter = RateLimiter(max_requests=5, window_seconds=10, burst_size=3)
        
        print("Testing rate limiter...\n")
        
        for i in range(8):
            start = time.time()
            await limiter.acquire()
            elapsed = time.time() - start
            
            stats = limiter.get_stats()
            print(
                f"Request {i+1}: waited {elapsed:.2f}s | "
                f"tokens={limiter.tokens:.1f} | "
                f"rpm={stats.avg_requests_per_min}"
            )
        
        print("\n✅ Rate limiter test complete")
    
    asyncio.run(test())
