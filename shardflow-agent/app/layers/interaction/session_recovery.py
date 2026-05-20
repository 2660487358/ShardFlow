"""Cross-window session resume and recovery."""
import json
from typing import Any

from app.infrastructure.redis_client import redis_client
from app.infrastructure.shard_cache import shard_cache


class SessionRecoveryManager:
    async def archive_with_shard_check(self, tenant_id: str, session_id: str, state: dict[str, Any]) -> dict[str, Any]:
        r = await redis_client.get_redis()
        session_key = f"kb:{tenant_id}:session:{session_id}"

        usage = state.get("context_usage_ratio", 0)
        task_id = state.get("task_id", "")

        if usage >= 0.80:
            from app.layers.agent_core.context_shard import context_shard_manager
            shard = await context_shard_manager.extract_shard(state)
            if shard:
                shard_data = shard.model_dump()
                state["shard_saved"] = True
                state["shard_id"] = shard_data.get("shard_id", "")

        await r.delete(session_key)
        if task_id:
            await r.publish(f"kb:{tenant_id}:events", json.dumps({
                "event": "session_archived",
                "task_id": task_id,
                "session_id": session_id,
            }))

        return state

    async def try_resume_session(self, tenant_id: str, task_id: str) -> dict[str, Any] | None:

        r = await redis_client.get_redis()
        prefix = f"kb:{tenant_id}:session:"
        async for key in r.scan_iter(match=f"{prefix}*", count=50):
            raw = await r.get(key)
            if raw:
                data: dict[str, Any] = json.loads(raw)
                if data.get("task_id") == task_id:
                    return data
        return None

    async def inject_shard_on_resume(self, tenant_id: str, task_id: str,
                                     state: dict[str, Any]) -> dict[str, Any]:
        from app.layers.agent_core.context_shard import context_shard_manager

        shard_data = await shard_cache.get_latest_shard(tenant_id, task_id)
        if shard_data is None:
            return state

        from app.models.context_shard import ContextShard
        shard = ContextShard(**shard_data)

        injected = context_shard_manager.inject_shard(shard, state)
        state["context_shard_info"] = injected
        state["shard_resumed"] = True
        state["resumed_shard"] = {
            "confirmed_count": len(shard.confirmed),
            "excluded_count": len(shard.excluded),
            "pending_count": len(shard.pending),
            "created_at": shard_data.get("created_at", ""),
        }
        return state


session_recovery = SessionRecoveryManager()
