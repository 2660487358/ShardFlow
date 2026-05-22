"""L0CacheAdapter — in-process LRU memory adapter implementing MemoryStore Protocol.

Wraps the existing L0Cache (OrderedDict-based LRU) for sub-millisecond reads.
Used as the first tier in CompositeAdapter's L0→L1→L2 degrade-read chain.

Key format: "{user_id}:{memory_type.value}:{key}"
"""
from datetime import datetime, timezone
from typing import Any

from app.infrastructure.l0_cache import L0Cache
from app.models.memory import MemoryRecord, MemoryQuery, MemoryType


class L0CacheAdapter:
    """Wraps L0Cache as a MemoryStore implementation for sub-ms local reads."""

    def __init__(self, max_size: int = 256) -> None:
        self._cache = L0Cache(max_size=max_size)

    def _build_key(self, user_id: str, memory_type: MemoryType, key: str) -> str:
        return f"{user_id}:{memory_type.value}:{key}"

    async def read(self, user_id: str, memory_type: MemoryType, key: str) -> MemoryRecord | None:
        cache_key = self._build_key(user_id, memory_type, key)
        record = self._cache.get(cache_key)
        if record is None:
            return None
        if isinstance(record, MemoryRecord):
            return record
        # Handle legacy dict entries (backward compat)
        if isinstance(record, dict):
            return MemoryRecord(key=key, user_id=user_id, memory_type=memory_type, data=record)
        return None

    async def write(self, user_id: str, memory_type: MemoryType, key: str,
                    data: dict[str, Any], ttl_seconds: int = 0) -> MemoryRecord:
        cache_key = self._build_key(user_id, memory_type, key)
        now = datetime.now(timezone.utc)
        record = MemoryRecord(
            key=key, user_id=user_id, memory_type=memory_type,
            data=data, ttl_seconds=ttl_seconds, updated_at=now,
        )
        self._cache.set(cache_key, record)
        return record

    async def delete(self, user_id: str, memory_type: MemoryType, key: str) -> bool:
        cache_key = self._build_key(user_id, memory_type, key)
        existed = self._cache.get(cache_key) is not None
        self._cache.invalidate(cache_key)
        return existed

    async def search(self, user_id: str, memory_type: MemoryType,
                     query: MemoryQuery) -> list[MemoryRecord]:
        # L0 is not optimized for search — delegate to higher tiers
        prefix = self._build_key(user_id, memory_type, "")
        results: list[MemoryRecord] = []
        for cache_key, record in list(self._cache._cache.items()):
            if cache_key.startswith(prefix) and isinstance(record, MemoryRecord):
                if not query.tags or any(t in record.tags for t in query.tags):
                    results.append(record)
        return sorted(results, key=lambda r: r.updated_at, reverse=True)[:query.limit]

    async def exists(self, user_id: str, memory_type: MemoryType, key: str) -> bool:
        cache_key = self._build_key(user_id, memory_type, key)
        return self._cache.get(cache_key) is not None
