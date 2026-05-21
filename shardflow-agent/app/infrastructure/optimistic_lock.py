"""Optimistic locking for concurrent shard writes via Redis Lua script CAS.

Uses a Redis Lua script to atomically check the current version and conditionally
update, implementing true Compare-And-Swap semantics.
"""
from typing import Any

from app.infrastructure.redis_client import redis_client

# Lua script: atomically compare expected version and set new version.
# KEYS[1] = version key
# ARGV[1] = expected version (0 means "key does not exist")
# ARGV[2] = new version value
# Returns: 1 if set (CAS success), 0 if version mismatch (conflict)
CAS_LUA_SCRIPT = """
local current = redis.call('GET', KEYS[1])
local expected = tonumber(ARGV[1])
local new_val = ARGV[2]
if (expected == 0 and current == false) or (current and tonumber(current) == expected) then
    redis.call('SET', KEYS[1], new_val)
    return 1
else
    return 0
end
"""


class OptimisticLock:
    LOCK_TTL: int = 30
    VERSION_TTL: int = 86400  # 24h

    def __init__(self) -> None:
        self._cas_sha: str | None = None

    async def _load_cas_script(self) -> str:
        """Load the CAS Lua script into Redis and cache its SHA."""
        if self._cas_sha is None:
            r = await redis_client.get_redis()
            self._cas_sha = await r.script_load(CAS_LUA_SCRIPT)
        return self._cas_sha

    async def acquire(self, tenant_id: str, task_id: str) -> bool:
        """Acquire a distributed lock with SETNX + TTL."""
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

    async def get_version(self, tenant_id: str, task_id: str) -> int:
        """Read current version (0 if key missing)."""
        r = await redis_client.get_redis()
        version_key = f"kb:{tenant_id}:shard:{task_id}:version"
        raw = await r.get(version_key)
        return int(raw) if raw else 0

    async def cas_update(self, tenant_id: str, task_id: str,
                         expected_version: int, new_version: int) -> bool:
        """Atomically update version iff current == expected_version.

        Returns True on successful CAS, False on conflict.
        """
        r = await redis_client.get_redis()
        version_key = f"kb:{tenant_id}:shard:{task_id}:version"
        sha = await self._load_cas_script()
        result = await r.evalsha(sha, 1, version_key, str(expected_version), str(new_version))
        return result == 1

    async def save_with_version_check(self, tenant_id: str, task_id: str,
                                      shard_data: dict[str, Any]) -> dict[str, Any]:
        """Compare-And-Swap version increment for shard writes.

        Reads current version, increments it, then atomically CAS-updates.
        On CAS conflict (another writer beat us), reads the new version and retries
        up to 3 times.
        """
        max_retries = 3
        for attempt in range(max_retries):
            current = await self.get_version(tenant_id, task_id)
            new_version = current + 1
            shard_data["version"] = new_version

            success = await self.cas_update(tenant_id, task_id, current, new_version)
            if success:
                return shard_data

            # CAS conflict — another writer updated; retry with fresh version
            if attempt < max_retries - 1:
                continue

        # Last resort: force-write version (pessimistic fallback)
        r = await redis_client.get_redis()
        version_key = f"kb:{tenant_id}:shard:{task_id}:version"
        new_version = await r.incr(version_key)
        await r.expire(version_key, self.VERSION_TTL)
        shard_data["version"] = new_version
        return shard_data


optimistic_lock = OptimisticLock()
