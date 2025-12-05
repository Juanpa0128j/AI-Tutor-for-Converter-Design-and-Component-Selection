"""Redis cache implementation for component data."""

from __future__ import annotations

import json
import logging
import os
from typing import List, Optional

logger = logging.getLogger(__name__)

try:
    import redis.asyncio as redis
    REDIS_AVAILABLE = True
except ImportError:
    REDIS_AVAILABLE = False

from tutor_virtual.domain.components import Component
from tutor_virtual.domain.ports import ComponentRepositoryPort


class RedisComponentCache(ComponentRepositoryPort):
    """Redis-based cache for component catalog data."""
    
    def __init__(
        self,
        host: Optional[str] = None,
        port: Optional[int] = None,
        db: Optional[int] = None,
        password: Optional[str] = None,
        default_ttl: Optional[int] = None
    ):
        """Initialize Redis connection."""
        if not REDIS_AVAILABLE:
            raise ImportError(
                "redis package is not installed. "
                "Install it with: pip install redis"
            )
        
        self.host = host or os.getenv("REDIS_HOST", "localhost")
        self.port = port or int(os.getenv("REDIS_PORT", "6379"))
        self.db = db or int(os.getenv("REDIS_DB", "0"))
        self.password = password or os.getenv("REDIS_PASSWORD")
        self.default_ttl = default_ttl or int(os.getenv("REDIS_CACHE_TTL", "86400"))
        
        self._redis: Optional[redis.Redis] = None
    
    async def _get_connection(self) -> redis.Redis:
        """Get or create Redis connection."""
        if self._redis is None:
            self._redis = redis.Redis(
                host=self.host,
                port=self.port,
                db=self.db,
                password=self.password if self.password else None,
                decode_responses=True
            )
        return self._redis
    
    async def get_cached_components(
        self,
        cache_key: str
    ) -> Optional[List[Component]]:
        """Retrieve cached component search results."""
        try:
            conn = await self._get_connection()
            cached_data = await conn.get(cache_key)
            
            if not cached_data:
                return None
            
            # Deserialize from JSON
            data = json.loads(cached_data)
            
            # Reconstruct Component objects
            # Note: This is simplified - real implementation would need
            # to reconstruct the correct component subclass (MOSFET, Diode, etc.)
            components = []
            for item in data:
                # TODO: Implement proper deserialization based on component type
                # For now, we'll need to add type information to the cache
                pass
            
            return components if components else None
            
        except Exception as e:
            # Log error but don't fail - cache miss is acceptable
            logger.error(f"Cache read error: {e}")
            return None
    
    async def cache_components(
        self,
        cache_key: str,
        components: List[Component],
        ttl_seconds: Optional[int] = None
    ) -> None:
        """Cache component search results."""
        try:
            conn = await self._get_connection()
            ttl = ttl_seconds or self.default_ttl
            
            # Serialize components to JSON
            # Note: dataclasses need custom serialization
            data = []
            for component in components:
                # Convert dataclass to dict
                item = {
                    "__type__": component.__class__.__name__,
                    **component.__dict__
                }
                data.append(item)
            
            await conn.setex(
                cache_key,
                ttl,
                json.dumps(data)
            )
            
        except Exception as e:
            # Log error but don't fail - cache write failure is acceptable
            logger.error(f"Cache write error: {e}")
    
    async def invalidate_cache(self, pattern: str) -> None:
        """Invalidate cache entries matching pattern."""
        try:
            conn = await self._get_connection()
            
            # Find all keys matching pattern
            keys = []
            async for key in conn.scan_iter(match=pattern):
                keys.append(key)
            
            # Delete matched keys
            if keys:
                await conn.delete(*keys)
                
        except Exception as e:
            logger.error(f"Cache invalidation error: {e}")
    
    async def close(self) -> None:
        """Close Redis connection."""
        if self._redis:
            await self._redis.close()
