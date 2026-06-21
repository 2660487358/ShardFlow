"""Memory management REST API for frontend integration.

S5.10: 记忆导出接口（FR-SM-004 / spec 7.10）。
- GET /api/v1/memory/export — Export all memory data for a user
"""
import logging
from typing import Any

from fastapi import APIRouter, Header, HTTPException, Query
from fastapi.responses import JSONResponse

from app.infrastructure.callback_client import callback_client

router = APIRouter(prefix="/memory", tags=["memory"])
logger = logging.getLogger(__name__)


@router.get("/export")
async def export_memory(
    x_user_id: str = Header(default=""),
    format: str = Query(default="json", description="Export format, only 'json' supported"),
) -> dict[str, Any]:
    """S5.10: Export all memory data for a user (spec 7.10).

    Returns memory_chunks, session_summaries, strategy_records, and
    user_profile for offline verification and data portability.
    SLA: 72 hours per spec 9.5.

    Args:
        x_user_id: User ID from header
        format: Export format (only 'json' supported)

    Returns:
        Export payload with export_time, user_id, memory_chunks,
        session_summaries, strategy_records, user_profile
    """
    if not x_user_id:
        raise HTTPException(status_code=400, detail="X-User-Id header is required")
    if format.lower() != "json":
        raise HTTPException(status_code=400, detail="Only 'json' format is supported")

    try:
        result = await callback_client.export_memory(user_id=x_user_id)
    except Exception as e:
        logger.error(f"Memory export failed for user={x_user_id}: {e}")
        raise HTTPException(status_code=502, detail=f"Memory export failed: {e}")

    if result.get("status") == "failed":
        raise HTTPException(status_code=502, detail=result.get("error", "export failed"))

    # Unwrap Java Result wrapper if present: {code, msg, data}
    data = result.get("data", result)
    return data
