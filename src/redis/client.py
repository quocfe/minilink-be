import redis.asyncio as redis
from typing import Optional
from src.config import settings


class RedisClient:
    def __init__(self):
        self._redis: Optional[redis.Redis] = None

    async def connect(self):
        """Connect to Redis."""
        self._redis = redis.from_url(
            settings.redis_url,
            encoding="utf-8",
            decode_responses=True
        )

    async def disconnect(self):
        """Disconnect from Redis."""
        if self._redis:
            await self._redis.close()

    async def get(self, key: str) -> Optional[str]:
        """Get value by key."""
        if not self._redis:
            await self.connect()
        return await self._redis.get(key)

    async def set(self, key: str, value: str, expire: int = None) -> bool:
        """Set key-value pair with optional expiration."""
        if not self._redis:
            await self.connect()
        return await self._redis.set(key, value, ex=expire)

    async def delete(self, key: str) -> int:
        """Delete key."""
        if not self._redis:
            await self.connect()
        return await self._redis.delete(key)

    async def incr(self, key: str) -> int:
        """Increment counter."""
        if not self._redis:
            await self.connect()
        return await self._redis.incr(key)

    async def expire(self, key: str, seconds: int) -> bool:
        """Set expiration on a key."""
        if not self._redis:
            await self.connect()
        return await self._redis.expire(key, seconds)

    async def ttl(self, key: str) -> int:
        """Get time-to-live for a key."""
        if not self._redis:
            await self.connect()
        return await self._redis.ttl(key)

    async def keys(self, pattern: str) -> list[str]:
        """Return all keys matching a pattern (use with care in production)."""
        if not self._redis:
            await self.connect()
        return await self._redis.keys(pattern)

    async def delete_many(self, *keys: str) -> int:
        """Delete multiple keys at once. Returns number of keys deleted."""
        if not self._redis:
            await self.connect()
        if not keys:
            return 0
        return await self._redis.delete(*keys)


# Global Redis client instance
redis_client = RedisClient()

