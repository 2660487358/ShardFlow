"""JavaAPIAdapter — HTTP callback adapter implementing MemoryStore Protocol.

Wraps callback_client for L2 tier persistence through Java kb-shard/kb-strategy services.
All writes go through idempotent POST callbacks.
"""
from datetime import datetime, timezone
from typing import Any

from app.infrastructure.callback_client import callback_client
from app.models.memory import MemoryRecord, MemoryQuery, MemoryType


class JavaAPIAdapter:
    """Java peripheral service adapter for L2 tier (50ms target)."""

    async def read(self, user_id: str, memory_type: MemoryType, key: str) -> MemoryRecord | None:
        if memory_type == MemoryType.LONG_TERM:
            try:
                result = await callback_client.get_shard(key)
                if result:
                    return MemoryRecord(
                        key=key, user_id=user_id, memory_type=memory_type,
                        data=result, version=result.get("version", 1),
                    )
            except Exception:
                return None
        elif memory_type == MemoryType.META:
            try:
                results = await callback_client.search_strategies(
                    task_type=key, query="", limit=1,
                )
                if results:
                    return MemoryRecord(
                        key=key, user_id=user_id, memory_type=memory_type,
                        data=results[0],
                    )
            except Exception:
                return None
        return None

    async def write(self, user_id: str, memory_type: MemoryType, key: str,
                    data: dict[str, Any], ttl_seconds: int = 0) -> MemoryRecord:
        now = datetime.now(timezone.utc)
        if memory_type == MemoryType.LONG_TERM:
            shard_data = {**data, "task_id": key, "user_id": user_id}
            try:
                await callback_client.save_shard(shard_data)
            except Exception:
                pass  # Degradation handled by CompositeAdapter
        elif memory_type == MemoryType.META:
            strategy_data = {**data, "strategy_id": key, "user_id": user_id}
            try:
                await callback_client.save_strategy(strategy_data)
            except Exception:
                pass

        return MemoryRecord(
            key=key, user_id=user_id, memory_type=memory_type,
            data=data, updated_at=now,
        )

    async def delete(self, user_id: str, memory_type: MemoryType, key: str) -> bool:
        # Java service doesn't support DELETE for shards/strategies via callback
        return False

    async def search(self, user_id: str, memory_type: MemoryType,
                     query: MemoryQuery) -> list[MemoryRecord]:
        if memory_type == MemoryType.META:
            try:
                results = await callback_client.search_strategies(
                    task_type=query.key_prefix or "", query="", limit=query.limit,
                )
                return [
                    MemoryRecord(key=r.get("strategy_id", ""), user_id=user_id,
                                 memory_type=memory_type, data=r)
                    for r in results
                ]
            except Exception:
                return []
        return []

    async def exists(self, user_id: str, memory_type: MemoryType, key: str) -> bool:
        record = await self.read(user_id, memory_type, key)
        return record is not None
