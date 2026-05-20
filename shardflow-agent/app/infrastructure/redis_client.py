import redis.asyncio as aioredis

from app.config import settings


async def get_redis() -> aioredis.Redis:
    return aioredis.from_url(settings.redis_url, decode_responses=False)


class RedisClient:
    def __init__(self) -> None:
        self._redis: aioredis.Redis | None = None

    async def connect(self) -> None:
        self._redis = await get_redis()

    async def disconnect(self) -> None:
        if self._redis:
            await self._redis.aclose()
            self._redis = None

    async def get_redis(self) -> aioredis.Redis:
        if self._redis is None:
            await self.connect()
        assert self._redis is not None
        return self._redis


redis_client = RedisClient()
