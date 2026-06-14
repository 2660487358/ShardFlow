"""RedisAdapter — Redis-backed memory adapter for L1 tier storage (< 2ms target)."""
import json
from datetime import datetime, timezone
from typing import Any

from app.infrastructure.redis_client import redis_client
from app.models.memory import MemoryRecord, MemoryQuery, MemoryType


class RedisAdapter:
    """Redis-backed adapter for L1 tier memory storage (< 2ms target)."""

    # ── Key builders ──

    def _build_key(self, user_id: str, memory_type: MemoryType, key: str) -> str:
        """Build Redis key for memory records."""
        return f"shardflow:{user_id}:mem:{memory_type.value}:{key}"

    def _build_summary_key(self, user_id: str, task_id: str) -> str:
        """Build Redis key for session state summary (latest version)."""
        return f"shardflow:{user_id}:sss:{task_id}:latest"

    # ── Serialization ──

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

    # ── CRUD ──

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
            # Use scan_iter with count=100 for better performance
            async for key in r.scan_iter(match=f"{prefix}*", count=100):
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

    # ── Pipeline batch operations ──

    async def batch_write(self, records: list[tuple[str, MemoryType, str, dict[str, Any], int]]) -> list[MemoryRecord]:
        """Batch write multiple records using Redis pipeline for reduced RTT."""
        r = await redis_client.get_redis()
        pipe = r.pipeline(transaction=False)
        now = datetime.now(timezone.utc)
        written: list[MemoryRecord] = []
        for user_id, memory_type, key, data, ttl_seconds in records:
            record = MemoryRecord(
                key=key, user_id=user_id, memory_type=memory_type,
                data=data, ttl_seconds=ttl_seconds, updated_at=now,
            )
            redis_key = self._build_key(user_id, memory_type, key)
            pipe.set(redis_key, self._serialize(record), ex=ttl_seconds if ttl_seconds > 0 else None)
            written.append(record)
        await pipe.execute()
        return written

    async def batch_read(self, user_id: str, memory_type: MemoryType,
                         keys: list[str]) -> list[MemoryRecord | None]:
        """Batch read multiple keys using Redis pipeline."""
        r = await redis_client.get_redis()
        pipe = r.pipeline(transaction=False)
        redis_keys = [self._build_key(user_id, memory_type, key) for key in keys]
        for rk in redis_keys:
            pipe.get(rk)
        raw_results = await pipe.execute()
        results: list[MemoryRecord | None] = []
        for raw in raw_results:
            if raw is None:
                results.append(None)
            else:
                results.append(self._deserialize(raw))
        return results

    async def batch_delete(self, user_id: str, memory_type: MemoryType,
                           keys: list[str]) -> int:
        """Delete multiple keys using Redis pipeline. Returns number of keys deleted."""
        r = await redis_client.get_redis()
        pipe = r.pipeline(transaction=False)
        redis_keys = [self._build_key(user_id, memory_type, key) for key in keys]
        for rk in redis_keys:
            pipe.delete(rk)
        results = await pipe.execute()
        return sum(results)

    async def batch_exists(self, user_id: str, memory_type: MemoryType,
                           keys: list[str]) -> dict[str, bool]:
        """Check existence of multiple keys using Redis pipeline.

        Returns:
            Dict mapping each key to its existence status.
        """
        r = await redis_client.get_redis()
        pipe = r.pipeline(transaction=False)
        redis_keys = [self._build_key(user_id, memory_type, key) for key in keys]
        for rk in redis_keys:
            pipe.exists(rk)
        results = await pipe.execute()
        return {key: count > 0 for key, count in zip(keys, results)}

    async def search_optimized(self, user_id: str, memory_type: MemoryType,
                               query: MemoryQuery) -> list[MemoryRecord]:
        """Optimized search using pipeline for batch GET after scan_iter.

        Instead of issuing individual GET commands per key found by scan_iter,
        collects all matching keys first, then batch-GETs them via pipeline.
        """
        r = await redis_client.get_redis()
        prefix = f"shardflow:{user_id}:mem:{memory_type.value}:"
        if query.key_prefix:
            prefix = f"{prefix}{query.key_prefix}"

        # Phase 1: Collect matching keys via scan_iter
        matched_keys: list[str] = []
        try:
            async for key in r.scan_iter(match=f"{prefix}*", count=100):
                matched_keys.append(key)
                if len(matched_keys) >= query.limit * 3:
                    break
        except Exception:
            return []

        if not matched_keys:
            return []

        # Phase 2: Batch GET all matched keys via pipeline
        pipe = r.pipeline(transaction=False)
        for key in matched_keys:
            pipe.get(key)
        raw_results = await pipe.execute()

        # Phase 3: Deserialize and filter
        results: list[MemoryRecord] = []
        for raw in raw_results:
            if raw is None:
                continue
            record = self._deserialize(raw)
            if not query.tags or any(t in record.tags for t in query.tags):
                results.append(record)
            if len(results) >= query.limit:
                break

        return sorted(results, key=lambda rec: rec.updated_at, reverse=True)[:query.limit]
