"""CompositeAdapter — L0→L1→L2 degrade-read + write-broadcast adapter.

Implements the four-tier memory architecture:
- Read:  L0 (local) → L1 (Redis) → L2 (Java API), backfilling on hit
- Write: Broadcast to L2 (authoritative) + L1 (cache) + L0 (local)

Memory types and their tier routing:
- SHORT_TERM:      L0 + L1 only (ephemeral session data)
- SESSION_SUMMARY: L0 + L1 + L2 (cross-session state snapshots)
- SEMANTIC:        L0 + L1 + L2 (user facts and preferences)
- EPISODIC:        L0 + L1 + L2 (decision paths and events)
"""
import logging
from datetime import datetime, timezone
from typing import Any

from app.infrastructure.memory_metrics import memory_metrics
from app.models.memory import MemoryRecord, MemoryQuery, MemoryType
from .l0_adapter import L0CacheAdapter
from .redis_adapter import RedisAdapter
from .java_adapter import JavaAPIAdapter

logger = logging.getLogger(__name__)


class CompositeAdapter:
    """Three-tier composite: L0 (sub-ms) → L1 (ms) → L2 (ms-to-Java).

    Supports four-layer memory model routing:
    - SHORT_TERM: L0 + L1 only
    - SESSION_SUMMARY / SEMANTIC / EPISODIC: full L0 → L1 → L2 chain
    """

    def __init__(self, use_l2: bool = True) -> None:
        self._l0 = L0CacheAdapter(max_size=256)
        self._l1 = RedisAdapter()
        self._l2 = JavaAPIAdapter() if use_l2 else None

    def _should_use_l2(self, memory_type: MemoryType) -> bool:
        return memory_type != MemoryType.SHORT_TERM and self._l2 is not None

    # ------------------------------------------------------------------
    # Read with degrade + backfill
    # ------------------------------------------------------------------

    async def read(self, user_id: str, memory_type: MemoryType, key: str) -> MemoryRecord | None:
        # L0: local LRU (< 0.1ms)
        record = await self._l0.read(user_id, memory_type, key)
        if record is not None:
            memory_metrics.record_hit("L0")
            return record
        memory_metrics.record_miss("L0")

        # L1: Redis (< 2ms)
        record = await self._l1.read(user_id, memory_type, key)
        if record is not None:
            memory_metrics.record_hit("L1")
            await self._l0.write(user_id, memory_type, key, record.data, record.ttl_seconds)
            return record
        memory_metrics.record_miss("L1")

        # L2: Java API (< 50ms) — only for non-ephemeral types
        if self._should_use_l2(memory_type):
            record = await self._l2.read(user_id, memory_type, key)
            if record is not None:
                memory_metrics.record_hit("L2")
                await self._l1.write(user_id, memory_type, key, record.data, record.ttl_seconds)
                await self._l0.write(user_id, memory_type, key, record.data, record.ttl_seconds)
                return record
            memory_metrics.record_miss("L2")

        return None

    # ------------------------------------------------------------------
    # Write broadcast (L2 authoritative → L1 cache → L0 local)
    # ------------------------------------------------------------------

    async def write(self, user_id: str, memory_type: MemoryType, key: str,
                    data: dict[str, Any], ttl_seconds: int = 0) -> MemoryRecord:
        now = datetime.now(timezone.utc)

        # L2: authoritative write — buffer failures for retry
        if self._should_use_l2(memory_type):
            try:
                l2_record = await self._l2.write(user_id, memory_type, key, data, ttl_seconds)
                if l2_record is None:
                    from app.layers.agent_core.memory_degradation import memory_degradation
                    await memory_degradation.buffer_write(
                        user_id, memory_type.value, key, data
                    )
            except Exception as e:
                logger.warning("L2 write exception (buffering for retry): %s", e)
                from app.layers.agent_core.memory_degradation import memory_degradation
                await memory_degradation.buffer_write(
                    user_id, memory_type.value, key, data
                )

        # L1: Redis cache
        try:
            await self._l1.write(user_id, memory_type, key, data, ttl_seconds)
        except Exception as e:
            logger.warning("L1 write failed: %s", e)

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
        if self._should_use_l2(memory_type):
            if await self._l2.delete(user_id, memory_type, key):
                deleted = True
        return deleted

    # ------------------------------------------------------------------
    # Search: route by memory type
    # ------------------------------------------------------------------

    async def search(self, user_id: str, memory_type: MemoryType,
                     query: MemoryQuery) -> list[MemoryRecord]:
        # For SEMANTIC/EPISODIC, prefer L2 (structured + vector search)
        if memory_type in (MemoryType.SEMANTIC, MemoryType.EPISODIC) and self._should_use_l2(memory_type):
            results = await self._l2.search(user_id, memory_type, query)
            if results:
                return results

        # For SESSION_SUMMARY/SHORT_TERM, search L1 (Redis) — use optimized pipeline search
        results = await self._l1.search_optimized(user_id, memory_type, query)
        if not results:
            results = await self._l0.search(user_id, memory_type, query)
        return results

    async def exists(self, user_id: str, memory_type: MemoryType, key: str) -> bool:
        if await self._l0.exists(user_id, memory_type, key):
            return True
        record = await self.read(user_id, memory_type, key)
        return record is not None
