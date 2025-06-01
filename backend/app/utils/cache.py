"""
Simple in-memory cache to replace Redis for local development.
"""

import asyncio
import json
import time
from typing import Any, Dict, Optional
from datetime import datetime, timedelta


class InMemoryCache:
    """Simple in-memory cache with TTL support."""
    
    def __init__(self):
        self._cache: Dict[str, Dict[str, Any]] = {}
        self._lock = asyncio.Lock()
    
    async def get(self, key: str) -> Optional[str]:
        """Get value from cache."""
        async with self._lock:
            if key in self._cache:
                entry = self._cache[key]
                if entry['expires_at'] is None or entry['expires_at'] > time.time():
                    return entry['value']
                else:
                    # Expired, remove it
                    del self._cache[key]
            return None
    
    async def set(self, key: str, value: str, ex: Optional[int] = None) -> bool:
        """Set value in cache with optional expiration."""
        async with self._lock:
            expires_at = None
            if ex is not None:
                expires_at = time.time() + ex
            
            self._cache[key] = {
                'value': value,
                'expires_at': expires_at
            }
            return True
    
    async def delete(self, key: str) -> int:
        """Delete key from cache."""
        async with self._lock:
            if key in self._cache:
                del self._cache[key]
                return 1
            return 0
    
    async def exists(self, key: str) -> bool:
        """Check if key exists in cache."""
        return await self.get(key) is not None
    
    async def expire(self, key: str, seconds: int) -> bool:
        """Set expiration for existing key."""
        async with self._lock:
            if key in self._cache:
                self._cache[key]['expires_at'] = time.time() + seconds
                return True
            return False
    
    async def ttl(self, key: str) -> int:
        """Get time to live for key."""
        async with self._lock:
            if key in self._cache:
                entry = self._cache[key]
                if entry['expires_at'] is None:
                    return -1  # No expiration
                ttl = int(entry['expires_at'] - time.time())
                return max(ttl, -2)  # -2 if expired
            return -2  # Key doesn't exist
    
    async def flushall(self) -> bool:
        """Clear all cache entries."""
        async with self._lock:
            self._cache.clear()
            return True
    
    async def keys(self, pattern: str = "*") -> list:
        """Get all keys matching pattern."""
        async with self._lock:
            if pattern == "*":
                return list(self._cache.keys())
            # Simple pattern matching (only supports * wildcard)
            import fnmatch
            return [key for key in self._cache.keys() if fnmatch.fnmatch(key, pattern)]
    
    def _cleanup_expired(self):
        """Remove expired entries."""
        current_time = time.time()
        expired_keys = []
        
        for key, entry in self._cache.items():
            if entry['expires_at'] is not None and entry['expires_at'] <= current_time:
                expired_keys.append(key)
        
        for key in expired_keys:
            del self._cache[key]


# Global cache instance
_cache_instance = None


async def get_cache() -> InMemoryCache:
    """Get cache instance."""
    global _cache_instance
    if _cache_instance is None:
        _cache_instance = InMemoryCache()
    return _cache_instance


class RedisCompatLayer:
    """Redis-compatible interface for the in-memory cache."""
    
    def __init__(self):
        self._cache = None
    
    async def _get_cache(self):
        if self._cache is None:
            self._cache = await get_cache()
        return self._cache
    
    async def get(self, key: str) -> Optional[bytes]:
        """Get value as bytes (Redis compatibility)."""
        cache = await self._get_cache()
        value = await cache.get(key)
        return value.encode() if value else None
    
    async def set(self, key: str, value: Any, ex: Optional[int] = None) -> bool:
        """Set value with optional expiration."""
        cache = await self._get_cache()
        if isinstance(value, bytes):
            value = value.decode()
        elif not isinstance(value, str):
            value = str(value)
        return await cache.set(key, value, ex)
    
    async def delete(self, key: str) -> int:
        """Delete key."""
        cache = await self._get_cache()
        return await cache.delete(key)
    
    async def exists(self, key: str) -> bool:
        """Check if key exists."""
        cache = await self._get_cache()
        return await cache.exists(key)
    
    async def expire(self, key: str, seconds: int) -> bool:
        """Set expiration."""
        cache = await self._get_cache()
        return await cache.expire(key, seconds)
    
    async def ttl(self, key: str) -> int:
        """Get TTL."""
        cache = await self._get_cache()
        return await cache.ttl(key)
    
    async def flushall(self) -> bool:
        """Clear all."""
        cache = await self._get_cache()
        return await cache.flushall()
    
    async def keys(self, pattern: str = "*") -> list:
        """Get keys."""
        cache = await self._get_cache()
        return await cache.keys(pattern)
    
    async def ping(self) -> bool:
        """Ping (always returns True for in-memory cache)."""
        return True
    
    async def close(self):
        """Close connection (no-op for in-memory cache)."""
        pass


# Create Redis-compatible instance
redis_client = RedisCompatLayer()