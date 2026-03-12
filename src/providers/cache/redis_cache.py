import os
from redis import asyncio as aioredis

class RedisCache:
    """Implementación de caché usando Redis."""
    def __init__(self, url: str):
        self.url = url
        self._redis = None

    async def get_connection(self):
        if not self._redis:
            self._redis = await aioredis.from_url(self.url, decode_responses=True)
        return self._redis

    async def get(self, key: str):
        conn = await self.get_connection()
        return await conn.get(key)

    async def set(self, key: str, value: str, ttl: int = 3600):
        conn = await self.get_connection()
        await conn.set(key, value, ex=ttl)

class RedisFactory:
    """Fábrica para obtener la instancia de caché."""
    @staticmethod
    def get_cache() -> RedisCache:
        redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
        return RedisCache(redis_url)