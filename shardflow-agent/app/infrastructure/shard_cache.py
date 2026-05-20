import json
from typing import Any

from app.config import settings
from app.infrastructure.callback_client import callback_client
from app.infrastructure.redis_client import redis_client


class ShardCache:
    """Three-tier shard cache: L0 (local memory) -> L1 (Redis direct) -> L2 (Java proxy)."""

    def __init__(self) -> None:
        self._local_cache: dict[str, dict[str, Any]] = {}

    def _cache_key(self, tenant_id: str, task_id: str) -> str:
        return f"{tenant_id}:{task_id}"

    def _redis_key(self, tenant_id: str, task_id: str) -> str:
        return f"kb:{tenant_id}:shard:{task_id}:latest"

    async def get_latest_shard(self, tenant_id: str, task_id: str) -> dict[str, Any] | None:
        cache_key = self._cache_key(tenant_id, task_id)

        if cache_key in self._local_cache:
            return self._local_cache[cache_key]

        r = await redis_client.get_redis()
        raw = await r.get(self._redis_key(tenant_id, task_id))
        if raw:
            shard: dict[str, Any] = json.loads(raw)
            self._local_cache[cache_key] = shard
            return shard

        result = await callback_client.get_shard(task_id)
        if result:
            self._local_cache[cache_key] = result
        return result

    async def save_shard(self, tenant_id: str, shard: dict[str, Any]) -> dict[str, Any]:
        task_id = shard["task_id"]
        result = await callback_client.save_shard(shard)

        cache_key = self._cache_key(tenant_id, task_id)
        self._local_cache[cache_key] = shard

        r = await redis_client.get_redis()
        await r.set(
            self._redis_key(tenant_id, task_id),
            json.dumps(shard),
            ex=settings.shard_cache_ttl,
        )

        return result

    def invalidate(self, tenant_id: str, task_id: str) -> None:
        self._local_cache.pop(self._cache_key(tenant_id, task_id), None)


shard_cache = ShardCache()
