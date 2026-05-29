"""Conversation endpoint with SSE streaming support."""
from typing import Any

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse

from app.api.v1.response_formatter import stream_react_events
from app.layers.interaction.entity_extractor import entity_extractor
from app.layers.interaction.intent_recognizer import intent_recognizer
from app.layers.interaction.session_manager import session_manager
from app.models.kb_state import create_initial_state

router = APIRouter()


class ConversationRequest(BaseModel):
    task_id: str
    message: str
    session_id: str = ""
    user_id: str = ""
    stream: bool = True
    context: dict[str, Any] | None = None


@router.post("/conversation")
async def handle_conversation(
    request: ConversationRequest,
    x_user_id: str = Header(default=""),
    x_session_id: str = Header(default=""),
    x_task_id: str = Header(default=""),
) -> Any:
    user_id = x_user_id or request.user_id
    if not user_id:
        raise HTTPException(status_code=400, detail="user_id is required")
    if not request.message or len(request.message) > 10000:
        raise HTTPException(status_code=400, detail="message must be non-empty and <= 10000 chars")

    # InputGuard: 安全检查
    from app.layers.security.input_guard import input_guard
    inspection = input_guard.inspect(request.message)
    if not inspection.passed and inspection.risk_level in ("HIGH", "CRITICAL"):
        raise HTTPException(status_code=400, detail=f"Input rejected: {'; '.join(inspection.reasons)}")

    session_id = x_session_id or request.session_id
    session = await session_manager.get_session(user_id, session_id) if session_id else None
    if session is None:
        session = await session_manager.create_session(user_id, request.task_id or x_task_id, session_id)
        session_id = session["session_id"]

    intent, confidence = await intent_recognizer.recognize_async(request.message)
    entities = await entity_extractor.extract_async(request.message)

    state = create_initial_state(
        task_id=request.task_id or x_task_id,
        user_id=user_id,
        session_id=session_id,
        user_input=request.message,
    )
    state["intent"] = intent
    state["entities"] = entities

    if request.stream:
        async def event_generator() -> Any:
            async for sse_msg in stream_react_events(state):
                yield sse_msg

        return EventSourceResponse(
            event_generator(),
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )

    return {
        "session_id": session_id,
        "intent": intent,
        "intent_confidence": confidence,
        "entities": entities,
        "state": {
            "token_count": state["token_count"],
            "context_usage_ratio": state["context_usage_ratio"],
            "loop_count": state["loop_count"],
        },
    }


@router.get("/conversation/{session_id}")
async def get_conversation(session_id: str, x_user_id: str = Header(default="")) -> dict[str, Any]:
    session = await session_manager.get_session(x_user_id, session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="session not found")
    return session
