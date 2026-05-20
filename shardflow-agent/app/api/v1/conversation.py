"""Conversation endpoint with SSE streaming support."""
from typing import Any

from fastapi import APIRouter, Header
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
    tenant_id: str = ""
    stream: bool = True
    context: dict[str, Any] | None = None


@router.post("/conversation")
async def handle_conversation(
    request: ConversationRequest,
    x_tenant_id: str = Header(default=""),
    x_session_id: str = Header(default=""),
    x_task_id: str = Header(default=""),
) -> Any:
    tenant_id = x_tenant_id or request.tenant_id
    if not tenant_id:
        return {"error": "tenant_id is required"}, 400
    if not request.message or len(request.message) > 10000:
        return {"error": "message must be non-empty and <= 10000 chars"}, 400

    session_id = x_session_id or request.session_id
    session = await session_manager.get_session(tenant_id, session_id) if session_id else None
    if session is None:
        session = await session_manager.create_session(tenant_id, request.task_id or x_task_id, session_id)
        session_id = session["session_id"]

    intent, confidence = await intent_recognizer.recognize_async(request.message)
    entities = await entity_extractor.extract_async(request.message)

    state = create_initial_state(
        task_id=request.task_id or x_task_id,
        tenant_id=tenant_id,
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
async def get_conversation(session_id: str, x_tenant_id: str = Header(default="")) -> dict[str, Any]:
    session = await session_manager.get_session(x_tenant_id, session_id)
    if session is None:
        return {"error": "session not found"}, 404  # type: ignore[return-value]
    return session
