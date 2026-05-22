"""RedisAdapter — Redis-backed MemoryStore implementation.

Key format: "shardflow:{user_id}:mem:{memory_type.value}:{key}"
Supports TTL via Redis EXPIRE.
"""
import json
from datetime import datetime, timezone
from typing import Any

from app.infrastructure.redis_client import redis_client
from app.models.memory import MemoryRecord, MemoryQuery, MemoryType


class RedisAdapter:
    """Redis-backed adapter for L1 tier memory storage (5ms target)."""

    def _build_key(self, user_id: str, memory_type: MemoryType, key: str) -> str:
        return f"shardflow:{user_id}:mem:{memory_type.value}:{key}"

    def _serialize(self, record: MemoryRecord) -> str:
        return json.dumps({
            "key": record.key, "user_id": record.user_id,
            "memory_type": record.memory_type.value, "data": record.data,
            "version": record.version, "ttl_seconds": record.ttl_seconds,
            "created_at": record.created_at.isoformat(),
            "updated_at": record.updated_at.isoformat(),
            "tags": record.tags,
        }, ensure_ascii=False)

    def _deserialize(self, raw: bytes | str) -> MemoryRecord:
        if isinstance(raw, bytes):
            raw = raw.decode("utf-8")
        d = json.loads(raw)
        return MemoryRecord(
            key=d["key"], user_id=d.get("user_id", ""),
            memory_type=MemoryType(d.get("memory_type", "short_term")),
            data=d.get("data", {}), version=d.get("version", 1),
            ttl_seconds=d.get("ttl_seconds", 0),
            created_at=datetime.fromisoformat(d["created_at"]) if d.get("created_at") else datetime.now(timezone.utc),
            updated_at=datetime.fromisoformat(d["updated_at"]) if d.get("updated_at") else datetime.now(timezone.utc),
            tags=d.get("tags", []),
        )

    async def read(self, user_id: str, memory_type: MemoryType, key: str) -> MemoryRecord | None:
        r = await redis_client.get_redis()
        raw = await r.get(self._build_key(user_id, memory_type, key))
        if raw is None:
            return None
        return self._deserialize(raw)

    async def write(self, user_id: str, memory_type: MemoryType, key: str,
                    data: dict[str, Any], ttl_seconds: int = 0) -> MemoryRecord:
        r = await redis_client.get_redis()
        now = datetime.now(timezone.utc)
        record = MemoryRecord(
            key=key, user_id=user_id, memory_type=memory_type,
            data=data, ttl_seconds=ttl_seconds, updated_at=now,
        )
        redis_key = self._build_key(user_id, memory_type, key)
        await r.set(redis_key, self._serialize(record), ex=ttl_seconds if ttl_seconds > 0 else None)
        return record

    async def delete(self, user_id: str, memory_type: MemoryType, key: str) -> bool:
        r = await redis_client.get_redis()
        result = await r.delete(self._build_key(user_id, memory_type, key))
        return result > 0

    async def search(self, user_id: str, memory_type: MemoryType,
                     query: MemoryQuery) -> list[MemoryRecord]:
        r = await redis_client.get_redis()
        prefix = f"shardflow:{user_id}:mem:{memory_type.value}:"
        if query.key_prefix:
            prefix = f"{prefix}{query.key_prefix}"
        results: list[MemoryRecord] = []
        try:
            async for key in r.scan_iter(match=f"{prefix}*", count=20):
                raw = await r.get(key)
                if raw:
                    record = self._deserialize(raw)
                    if not query.tags or any(t in record.tags for t in query.tags):
                        results.append(record)
                    if len(results) >= query.limit:
                        break
        except Exception:
            pass
        return sorted(results, key=lambda r: r.updated_at, reverse=True)[:query.limit]

    async def exists(self, user_id: str, memory_type: MemoryType, key: str) -> bool:
        r = await redis_client.get_redis()
        return await r.exists(self._build_key(user_id, memory_type, key)) > 0
