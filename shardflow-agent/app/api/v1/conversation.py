"""Conversation endpoint with SSE streaming support."""
from typing import Any

from fastapi import APIRouter, Header, HTTPException, Request
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
    model: str = ""  # model_id for routing
    kb_collection_name: str = ""
    kb_id: str = ""  # Knowledge base collection ID for filtering within Milvus collection
    stream: bool = True
    context: dict[str, Any] | None = None
    token_budget: int = 4096  # 记忆注入 Token 预算（与模型上下文限制解耦）


@router.post("/conversation")
async def handle_conversation(
    fastapi_request: Request,
    body: ConversationRequest,
    x_user_id: str = Header(default=""),
    x_session_id: str = Header(default=""),
    x_task_id: str = Header(default=""),
) -> Any:
    user_id = x_user_id or body.user_id
    if not user_id:
        raise HTTPException(status_code=400, detail="user_id is required")
    if not body.message or len(body.message) > 10000:
        raise HTTPException(status_code=400, detail="message must be non-empty and <= 10000 chars")

    from app.layers.security.input_guard import input_guard
    inspection = input_guard.inspect(body.message)
    if not inspection.passed and inspection.risk_level in ("HIGH", "CRITICAL"):
        raise HTTPException(status_code=400, detail=f"Input rejected: {'; '.join(inspection.reasons)}")

    session_id = x_session_id or body.session_id
    # T1.2: 当传入的 session_id 为空或在 Redis 中不存在时，自动创建新 session
    # 保留用户指定值，冲突时后端重新生成
    session = await session_manager.get_session(user_id, session_id) if session_id else None
    if session is None:
        session = await session_manager.create_session(
            user_id,
            body.task_id or x_task_id,
            session_id,
        )
        session_id = session["session_id"]

    intent, confidence = await intent_recognizer.recognize_async(body.message)
    entities = await entity_extractor.extract_async(body.message)

    state = create_initial_state(
        task_id=body.task_id or x_task_id,
        user_id=user_id,
        session_id=session_id,
        user_input=body.message,
    )
    state["intent"] = intent
    state["entities"] = entities
    state["model_id"] = body.model or "gpt-4o"
    state["kb_collection_name"] = body.kb_collection_name
    state["kb_id"] = body.kb_id

    # ── 记忆注入链路（2A-01/02/03/04, 3C-03, 4A-05, 4C-02）──
    # 所有记忆操作通过 MemoryCircuitBreaker 保护
    # 4A-05: memory_enabled 总开关，一键关闭记忆系统
    # 4C-02: A/B 测试分组决定是否注入记忆上下文
    from app.config import settings
    memory_should_inject = settings.memory_enabled

    # 4C-02: A/B 测试 — control 组不注入记忆
    if memory_should_inject and settings.memory_ab_enabled:
        if settings.memory_ab_group == "control":
            memory_should_inject = False

    if memory_should_inject:
        try:
            from app.layers.agent_core.memory_circuit_breaker import get_memory_circuit_breaker
            cb = get_memory_circuit_breaker()

            # 2A-04: 流式开始前预加载 working memory session
            from app.layers.agent_core.working_memory_manager import working_memory_manager
            wm = working_memory_manager.get_session(session_id)
            if wm is None:
                wm = await cb.call(
                    working_memory_manager.load_from_l1, user_id, session_id,
                )
            if wm is None:
                wm = working_memory_manager.create_session(
                    user_id=user_id, session_id=session_id,
                    task_id=body.task_id or x_task_id,
                )

            # FIX-1: 用户消息写入 WorkingMemory (FR-WM-001)
            # entities 类型: dict[str, list[str]]，需要扁平化为字符串列表供 metadata 使用
            _entity_list: list[str] = []
            if entities:
                for _vals in entities.values():
                    if isinstance(_vals, list):
                        _entity_list.extend(_vals)
            working_memory_manager.add_message(
                session_id,
                "user",
                body.message,
                metadata={
                    "intent": intent,
                    "entities": _entity_list,
                },
            )

            # FIX-5: 用户消息写入后持久化到 L1 (FR-WM-002)
            await working_memory_manager._persist_to_l1(wm)

            # 2A-01: ContextAssembler 组装记忆上下文
            from app.layers.agent_core.context_assembler import context_assembler
            assembly_result = await cb.call(
                context_assembler.assemble,
                user_id=user_id,
                session_id=session_id,
                task_id=body.task_id or x_task_id,
                query=body.message,
                token_budget=body.token_budget,
            )

            # 4A-04: assembly_result 是 AssembledContext Pydantic 对象
            if assembly_result is not None:
                # Extract section contents from AssembledContext
                section_map = {s.section_type: s.content for s in assembly_result.sections}
                state["context_shard_info"] = section_map.get("system", "")
                state["profile_context"] = section_map.get("profile", "")
                state["episodic_context"] = section_map.get("episodic", "")

            # 2A-03: 跨会话恢复
            from app.layers.interaction.session_recovery import session_recovery
            recovery_result = await cb.call(
                session_recovery.try_resume_session, user_id, body.task_id or x_task_id,
            )
            if recovery_result and recovery_result.get("resumed"):
                # 恢复成功时 context_shard_info 优先级高于通用组装
                state["context_shard_info"] = recovery_result.get("injection_text", state["context_shard_info"])

        except Exception as e:
            import logging
            logging.getLogger(__name__).warning("Memory injection failed (non-critical): %s", e)

    if body.stream:
        async def event_generator() -> Any:
            # T1.1: 传入 session_id/task_id 以便 SSE 首事件回传 session_info
            async for sse_msg in stream_react_events(
                state,
                request=fastapi_request,
                intent_confidence=confidence,
                session_id=session_id,
                task_id=body.task_id or x_task_id,
            ):
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
