"""上下文切换 API — 提取状态、持久化快照、返回新会话信息。"""
import logging
import uuid
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/context", tags=["context"])


class ContextSwitchRequest(BaseModel):
    user_id: str
    task_id: str
    session_id: str
    # Reserved for V1.1 — preview path feature
    preview_enabled: bool = False
    # Reserved for V1.1 — preview path feature
    preview_selections: dict[str, bool] | None = None


class ContextSwitchResponse(BaseModel):
    summary_id: str
    new_session_id: str
    status: str


@router.post("/switch", response_model=ContextSwitchResponse)
async def switch_context(req: ContextSwitchRequest) -> dict[str, Any]:
    """提取当前会话状态，持久化快照，返回新会话 ID。

    前端收到响应后：
    1. 关闭当前会话
    2. 使用 new_session_id 进入新会话页面
    3. 新会话启动时自动调用注入 API 加载快照
    """
    from app.layers.agent_core.working_memory_manager import working_memory_manager
    from app.layers.agent_core.session_state_summary_manager import session_state_summary_manager
    from app.layers.agent_core.memory_orchestrator import memory_orchestrator

    try:
        # 1. 获取当前短期记忆数据
        wm_data = working_memory_manager.get_session(req.session_id)
        if wm_data is None:
            raise HTTPException(
                status_code=400,
                detail=f"Unknown or stale session_id: {req.session_id}",
            )

        # 2. 将 MessageItem 列表转换为 dict 列表（extract_summary 要求 list[dict]）
        messages_dicts = [
            {"role": m.role, "content": m.content, "metadata": m.metadata}
            for m in wm_data.messages
        ]

        # 3. 提取会话状态快照
        summary = await session_state_summary_manager.extract_summary(
            user_id=req.user_id,
            task_id=req.task_id,
            session_seq=1,
            task_type=wm_data.task_type or "continue",
            task_goal=wm_data.intent_stack[0] if wm_data.intent_stack else "",
            messages=messages_dicts,
            context_summary=wm_data.context_summary or "",
            intent_stack=wm_data.intent_stack,
            trigger=session_state_summary_manager.TRIGGER_USER_REQUEST,
        )

        # 4. 持久化快照（write_summary 签名: user_id, task_id, summary_data）
        await memory_orchestrator.write_summary(
            req.user_id, req.task_id, summary.model_dump(mode="json")
        )

        # 5. 生成新会话 ID
        new_session_id = f"sess_{uuid.uuid4().hex[:12]}"

        return {
            "summary_id": summary.summary_id,
            "new_session_id": new_session_id,
            "status": "ready",
        }

    except Exception as e:
        logger.exception("Context switch failed")
        raise HTTPException(status_code=500, detail=f"上下文切换失败: {e}")
