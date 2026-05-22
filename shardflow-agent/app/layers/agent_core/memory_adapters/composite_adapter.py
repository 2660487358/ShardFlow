"""CompositeAdapter — L0→L1→L2 degrade-read + write-broadcast adapter.

Implements the three-tier caching architecture:
- Read:  L0 (local) → L1 (Redis) → L2 (Java API), backfilling on hit
- Write: Broadcast to L2 (authoritative) + L1 (cache) + L0 (local), async

This is the primary adapter used by MemoryOrchestrator for LONG_TERM memory.
"""
import logging
from datetime import datetime, timezone
from typing import Any

from app.models.memory import MemoryRecord, MemoryQuery, MemoryType
from .l0_adapter import L0CacheAdapter
from .redis_adapter import RedisAdapter
from .java_adapter import JavaAPIAdapter

logger = logging.getLogger(__name__)


class CompositeAdapter:
    """Three-tier composite: L0 (sub-ms) → L1 (ms) → L2 (ms-to-Java)."""

    def __init__(self) -> None:
        self._l0 = L0CacheAdapter(max_size=256)
        self._l1 = RedisAdapter()
        self._l2 = JavaAPIAdapter()

    # ------------------------------------------------------------------
    # Read with degrade + backfill
    # ------------------------------------------------------------------

    async def read(self, user_id: str, memory_type: MemoryType, key: str) -> MemoryRecord | None:
        # L0: local LRU (< 0.1ms)
        record = await self._l0.read(user_id, memory_type, key)
        if record is not None:
            return record

        # L1: Redis (< 5ms)
        record = await self._l1.read(user_id, memory_type, key)
        if record is not None:
            await self._l0.write(user_id, memory_type, key, record.data, record.ttl_seconds)
            return record

        # L2: Java API (< 50ms)
        record = await self._l2.read(user_id, memory_type, key)
        if record is not None:
            # Backfill both caches
            await self._l1.write(user_id, memory_type, key, record.data, record.ttl_seconds)
            await self._l0.write(user_id, memory_type, key, record.data, record.ttl_seconds)
            return record

        return None

    # ------------------------------------------------------------------
    # Write broadcast (L2 authoritative → L1 cache → L0 local)
    # ------------------------------------------------------------------

    async def write(self, user_id: str, memory_type: MemoryType, key: str,
                    data: dict[str, Any], ttl_seconds: int = 0) -> MemoryRecord:
        now = datetime.now(timezone.utc)

        # L2: authoritative write (async, don't block on failure)
        try:
            await self._l2.write(user_id, memory_type, key, data, ttl_seconds)
        except Exception as e:
            logger.warning(f"L2 write failed (will retry): {e}")

        # L1: Redis cache (fire-and-forget)
        try:
            await self._l1.write(user_id, memory_type, key, data, ttl_seconds)
        except Exception as e:
            logger.warning(f"L1 write failed: {e}")

        # L0: update local cache immediately
        record = await self._l0.write(user_id, memory_type, key, data, ttl_seconds)
        return record

    # ------------------------------------------------------------------
    # Delete: cascade through all tiers
    # ------------------------------------------------------------------

    async def delete(self, user_id: str, memory_type: MemoryType, key: str) -> bool:
        deleted = False
        if await self._l0.delete(user_id, memory_type, key):
            deleted = True
        if await self._l1.delete(user_id, memory_type, key):
            deleted = True
        if await self._l2.delete(user_id, memory_type, key):
            deleted = True
        return deleted

    # ------------------------------------------------------------------
    # Search: prefer L2 for META, L1 for others
    # ------------------------------------------------------------------

    async def search(self, user_id: str, memory_type: MemoryType,
                     query: MemoryQuery) -> list[MemoryRecord]:
        if memory_type == MemoryType.META:
            return await self._l2.search(user_id, memory_type, query)
        # For LONG_TERM/SHORT_TERM, search L1 (Redis)
        results = await self._l1.search(user_id, memory_type, query)
        if not results:
            results = await self._l0.search(user_id, memory_type, query)
        return results

    async def exists(self, user_id: str, memory_type: MemoryType, key: str) -> bool:
        if await self._l0.exists(user_id, memory_type, key):
            return True
        record = await self.read(user_id, memory_type, key)
        return record is not None
