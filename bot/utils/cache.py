"""
Smart Caching System
====================
Redis-based cache avec fallback in-memory si Redis indisponible.
Support TTL, invalidation par pattern, et async-first design.

Usage:
    from bot.utils.cache import get_cache_service
    
    cache = get_cache_service()
    
    # Get
    value = await cache.get("market:0x123")
    
    # Set avec TTL
    await cache.set("market:0x123", data, ttl=300)
    
    # Invalidate pattern
    await cache.invalidate("market:*")
"""
import json
import time
from typing import Any, Optional
from functools import lru_cache

from bot.utils.logger import logger


class InMemoryCache:
    """Fallback cache in-memory si Redis indisponible."""
    
    def __init__(self):
        self._cache: dict[str, tuple[Any, float]] = {}
    
    def get(self, key: str) -> Optional[Any]:
        """Get cached value if not expired."""
        if key not in self._cache:
            return None
        
        value, expires_at = self._cache[key]
        if time.time() > expires_at:
            del self._cache[key]
            return None
        
        return value
    
    def set(self, key: str, value: Any, ttl: int):
        """Set cache with TTL (seconds)."""
        expires_at = time.time() + ttl
        self._cache[key] = (value, expires_at)
    
    def delete(self, key: str):
        """Delete single key."""
        self._cache.pop(key, None)
    
    def invalidate(self, pattern: str):
        """Clear cache by pattern (simple prefix match)."""
        prefix = pattern.rstrip("*")
        keys_to_delete = [k for k in self._cache if k.startswith(prefix)]
        for key in keys_to_delete:
            del self._cache[key]
    
    def clear(self):
        """Clear all cache."""
        self._cache.clear()


class CacheService:
    """
    Smart cache avec Redis + fallback in-memory.
    Thread-safe, async-friendly, auto-serialization JSON.
    """
    
    def __init__(self, redis_url: Optional[str] = None):
        self.redis = None
        self.fallback = InMemoryCache()
        
        if redis_url:
            try:
                import redis
                self.redis = redis.from_url(redis_url, decode_responses=True, socket_connect_timeout=2)
                self.redis.ping()
                logger.info("[CACHE] Redis connected successfully")
            except Exception as e:
                logger.warning(f"[CACHE] Redis unavailable ({e}), using in-memory fallback")
                self.redis = None
    
    async def get(self, key: str) -> Optional[Any]:
        """
        Get cached value.
        Returns None si absent ou expiré.
        """
        try:
            if self.redis:
                val = self.redis.get(key)
                if val:
                    return json.loads(val)
                return None
            else:
                return self.fallback.get(key)
        except Exception as e:
            logger.debug(f"[CACHE] get error {key[:20]}: {e}")
            return None
    
    async def set(self, key: str, value: Any, ttl: int = 300):
        """
        Set cache avec TTL (secondes).
        Auto-sérialise en JSON.
        
        Args:
            key: Cache key
            value: Data à cacher (doit être JSON-serializable)
            ttl: Time-to-live en secondes (défaut: 5min)
        """
        try:
            if self.redis:
                self.redis.setex(key, ttl, json.dumps(value, default=str))
            else:
                self.fallback.set(key, value, ttl)
        except Exception as e:
            logger.debug(f"[CACHE] set error {key[:20]}: {e}")
    
    async def delete(self, key: str):
        """Delete single cache key."""
        try:
            if self.redis:
                self.redis.delete(key)
            else:
                self.fallback.delete(key)
        except Exception as e:
            logger.debug(f"[CACHE] delete error {key[:20]}: {e}")
    
    async def invalidate(self, pattern: str):
        """
        Clear cache by pattern.
        
        Examples:
            await cache.invalidate("market:*")     # All markets
            await cache.invalidate("wallet:0x*")   # All wallets
            await cache.invalidate("*")            # Everything
        
        Args:
            pattern: Redis pattern (*, ?, [...])
        """
        try:
            if self.redis:
                keys = list(self.redis.scan_iter(match=pattern, count=1000))
                if keys:
                    self.redis.delete(*keys)
                    logger.debug(f"[CACHE] Invalidated {len(keys)} keys matching {pattern}")
            else:
                self.fallback.invalidate(pattern)
        except Exception as e:
            logger.debug(f"[CACHE] invalidate error {pattern}: {e}")
    
    async def clear(self):
        """Clear ALL cache (use with caution)."""
        try:
            if self.redis:
                self.redis.flushdb()
                logger.info("[CACHE] Redis cache cleared")
            else:
                self.fallback.clear()
                logger.info("[CACHE] In-memory cache cleared")
        except Exception as e:
            logger.warning(f"[CACHE] clear error: {e}")


# ── Singleton cache service ────────────────────────────────────────────────

_cache_service: Optional[CacheService] = None


@lru_cache()
def get_cache_service() -> CacheService:
    """
    Get singleton cache service.
    Auto-initialise avec REDIS_URL depuis settings.
    """
    global _cache_service
    
    if _cache_service is None:
        from bot.config import get_settings
        settings = get_settings()
        _cache_service = CacheService(redis_url=settings.redis_url)
    
    return _cache_service


# ── Cache TTL presets ──────────────────────────────────────────────────────

class CacheTTL:
    """Presets TTL pour différents types de données."""
    
    MARKET_INFO = 300        # 5 minutes (marchés changent peu)
    WALLET_PROFILE = 300     # 5 minutes (usernames stables)
    WALLET_TRADES = 10       # 10 secondes (trades temps réel)
    WALLET_STATS = 60        # 1 minute (stats agrégées)
    TOKEN_PRICE = 5          # 5 secondes (prix volatils)
    CLOB_ORDERS = 3          # 3 secondes (order book rapide)
    NEWS_ARTICLES = 1800     # 30 minutes (actualités)
    DISCOVERY_WALLETS = 3600 # 1 heure (discovery lent)
