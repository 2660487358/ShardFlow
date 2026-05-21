"""Session management REST API for frontend integration."""
import json
import logging
from typing import Any

from fastapi import APIRouter, Header, HTTPException
from fastapi.responses import JSONResponse

from app.infrastructure.redis_client import redis_client

router = APIRouter(prefix="/sessions", tags=["sessions"])
logger = logging.getLogger(__name__)


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
    except Exception as e:
        logger.warning(f"Failed to list sessions for tenant={x_tenant_id}: {e}")
    return {"sessions": sessions, "total": len(sessions)}


@router.get("/{session_id}")
async def get_session(session_id: str, x_tenant_id: str = Header(default="")) -> Any:
    r = await redis_client.get_redis()
    raw = await r.get(f"kb:{x_tenant_id}:session:{session_id}")
    if raw is None:
        raise HTTPException(status_code=404, detail="session not found")
    data: dict[str, Any] = json.loads(raw)
    return data


@router.delete("/{session_id}")
async def close_session(session_id: str, x_tenant_id: str = Header(default="")) -> dict[str, Any]:
    from app.layers.interaction.session_manager import session_manager
    await session_manager.archive_session(x_tenant_id, session_id)
    return {"status": "archived", "session_id": session_id}


@router.get("/{session_id}/shards")
async def get_session_shards(session_id: str, x_tenant_id: str = Header(default="")) -> dict[str, Any]:
    """Get shards filtered by session_id, not all tenant shards."""
    r = await redis_client.get_redis()
    # Filter by task_id extracted from session, falling back to session-level shard key
    session_raw = await r.get(f"kb:{x_tenant_id}:session:{session_id}")
    if session_raw is None:
        return {"shards": [], "total": 0}

    session_data = json.loads(session_raw)
    task_id = session_data.get("task_id", "")

    shards: list[dict[str, Any]] = []
    try:
        if task_id:
            # Fetch latest shard for this task
            shard_raw = await r.get(f"kb:{x_tenant_id}:shard:{task_id}:latest")
            if shard_raw:
                shards.append(json.loads(shard_raw))
    except Exception as e:
        logger.warning(f"Failed to get shards for session={session_id}: {e}")
    return {"shards": shards, "total": len(shards)}
