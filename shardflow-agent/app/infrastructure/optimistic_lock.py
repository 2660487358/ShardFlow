"""Optimistic locking for concurrent shard writes."""
from typing import Any

from app.infrastructure.redis_client import redis_client


class OptimisticLock:
    LOCK_TTL: int = 30

    async def acquire(self, tenant_id: str, task_id: str) -> bool:
        r = await redis_client.get_redis()
        lock_key = f"kb:{tenant_id}:lock:shard:{task_id}"
        acquired = await r.setnx(lock_key, "1")
        if acquired:
            await r.expire(lock_key, self.LOCK_TTL)
        return bool(acquired)

    async def release(self, tenant_id: str, task_id: str) -> None:
        r = await redis_client.get_redis()
        lock_key = f"kb:{tenant_id}:lock:shard:{task_id}"
        await r.delete(lock_key)

    async def save_with_version_check(self, tenant_id: str, task_id: str,
                                      shard_data: dict[str, Any]) -> dict[str, Any]:
        r = await redis_client.get_redis()
        version_key = f"kb:{tenant_id}:shard:{task_id}:version"
        current_version = await r.get(version_key)
        current_version = int(current_version) if current_version else 0

        new_version = current_version + 1
        shard_data["version"] = new_version

        success = await r.setnx(version_key, str(new_version))
        if not success:
            await r.set(version_key, str(new_version))

        return shard_data


optimistic_lock = OptimisticLock()
