"""Session management REST API for frontend integration."""
import json
from typing import Any

from fastapi import APIRouter, Header

from app.infrastructure.redis_client import redis_client

router = APIRouter(prefix="/sessions", tags=["sessions"])


@router.get("")
async def list_sessions(x_tenant_id: str = Header(default="")) -> dict[str, Any]:
    r = await redis_client.get_redis()
    prefix = f"kb:{x_tenant_id}:session:"
    sessions: list[dict[str, Any]] = []
    try:
        async for key in r.scan_iter(match=f"{prefix}*", count=20):
            raw = await r.get(key)
            if raw:
                data = json.loads(raw)
                sessions.append({
                    "session_id": data.get("session_id"),
                    "task_id": data.get("task_id"),
                    "created_at": data.get("created_at"),
                    "last_active": data.get("last_active"),
                    "loop_count": data.get("state", {}).get("loop_count", 0),
                })
    except Exception:
        pass
    return {"sessions": sessions, "total": len(sessions)}


@router.get("/{session_id}")
async def get_session(session_id: str, x_tenant_id: str = Header(default="")) -> Any:
    r = await redis_client.get_redis()
    raw = await r.get(f"kb:{x_tenant_id}:session:{session_id}")
    if raw is None:
        return {"error": "session not found"}, 404
    data: dict[str, Any] = json.loads(raw)
    return data


@router.delete("/{session_id}")
async def close_session(session_id: str, x_tenant_id: str = Header(default="")) -> dict[str, Any]:
    from app.layers.interaction.session_manager import session_manager
    await session_manager.archive_session(x_tenant_id, session_id)
    return {"status": "archived", "session_id": session_id}


@router.get("/{session_id}/shards")
async def get_session_shards(session_id: str, x_tenant_id: str = Header(default="")) -> dict[str, Any]:
    r = await redis_client.get_redis()
    pattern = f"kb:{x_tenant_id}:shard:*:latest"
    shards: list[dict[str, Any]] = []
    try:
        async for key in r.scan_iter(match=pattern, count=10):
            raw = await r.get(key)
            if raw:
                shards.append(json.loads(raw))
    except Exception:
        pass
    return {"shards": shards, "total": len(shards)}
