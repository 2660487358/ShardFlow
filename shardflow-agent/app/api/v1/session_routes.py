"""Session lifecycle REST API: pre-creation, history recovery, expiry hints.

阶段2 P1 会话生命周期增强：
- POST /sessions/init              预创建 Session（用户进入 Chat 页即可获取 session_id）
- GET  /sessions/{id}/messages     历史消息恢复（支持分页 + user_id 鉴权 + L1→L2 降级）

设计要点：
- 复用 session_manager.create_session，session 元数据写入
  Redis `shardflow:{user}:mem:short_term:session:{sid}`，与 WorkingMemory 快照 key 分离。
- 限流：10 QPS/用户，超限返回 429（基于 Redis 滑动窗口）。
- 鉴权：user_id 从 X-User-Id Header 获取，禁止前端伪造；越权访问记录审计日志。
- 性能：预创建接口 RTT < 100ms；历史接口 P99 < 50ms。
"""
import json
import logging
import time
import uuid
from typing import Any

from fastapi import APIRouter, Header, HTTPException, Query
from pydantic import BaseModel, Field

from app.infrastructure.redis_client import redis_client
from app.layers.agent_core.working_memory_manager import (
    SESSION_WINDOW_KEY_PATTERN,
    working_memory_manager,
)
from app.layers.interaction.session_manager import session_manager
from app.layers.security.audit_logger import audit_logger

router = APIRouter(prefix="/sessions", tags=["sessions"])
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 限流配置（T2.2）
# ---------------------------------------------------------------------------

SESSION_INIT_RATE_LIMIT_QPS = 10  # 每用户 10 QPS
SESSION_INIT_RATE_LIMIT_WINDOW = 1  # 滑动窗口 1 秒


async def _check_rate_limit(user_id: str) -> bool:
    """基于 Redis 滑动窗口检查 user 维度限流。

    Returns:
        True 表示放行；False 表示超限。
    """
    try:
        r = await redis_client.get_redis()
        key = f"shardflow:{user_id}:ratelimit:sessions_init"
        now = time.time()
        window_start = now - SESSION_INIT_RATE_LIMIT_WINDOW
        # 使用单独命令而非 pipeline，提升与 fakeredis 的兼容性
        await r.zremrangebyscore(key, 0, window_start)
        # 使用 uuid 后缀确保 member 唯一，避免同时间戳覆盖
        member = f"{now}_{uuid.uuid4().hex[:8]}"
        await r.zadd(key, {member: now})
        await r.expire(key, SESSION_INIT_RATE_LIMIT_WINDOW + 1)
        count = await r.zcard(key)
        return count <= SESSION_INIT_RATE_LIMIT_QPS
    except Exception as e:
        # 限流失败时降级为放行，避免 Redis 故障阻断主流程
        logger.warning("Rate limit check failed (allowing request): %s", e)
        return True


# ---------------------------------------------------------------------------
# 请求/响应模型
# ---------------------------------------------------------------------------

class SessionCreateRequest(BaseModel):
    """预创建 Session 请求体。"""
    task_id: str = Field(default="", description="任务 ID，缺省时由后端生成")
    title: str = Field(default="", description="会话标题（可选）")
    source_port: str = Field(default="web", description="来源端口：web|mcp|api")
    metadata: dict[str, Any] = Field(default_factory=dict, description="附加元数据")


class SessionCreateData(BaseModel):
    session_id: str
    task_id: str
    created_at: str
    expires_at: str
    ttl_seconds: int


class SessionCreateResponse(BaseModel):
    code: int = 200
    data: SessionCreateData


class SessionMessageItem(BaseModel):
    """历史消息项。"""
    msg_id: str
    role: str
    content: str
    timestamp: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class SessionMessagesData(BaseModel):
    session_id: str
    messages: list[SessionMessageItem]
    has_more: bool
    next_before_msg_id: str | None = None


class SessionMessagesResponse(BaseModel):
    code: int = 200
    data: SessionMessagesData


# ---------------------------------------------------------------------------
# T2.1: 预创建 Session 接口
# ---------------------------------------------------------------------------

@router.post("/init", response_model=SessionCreateResponse)
async def init_session(
    body: SessionCreateRequest,
    x_user_id: str = Header(default=""),
) -> SessionCreateResponse:
    """预创建 Session，返回 session_id/task_id/created_at/expires_at。

    使用场景：用户进入 Chat 页面时即可调用，避免首条消息时序竞态。
    失败时前端降级为首条消息由 `/conversation` 兜底创建。

    性能目标：RTT < 100ms。
    """
    if not x_user_id:
        raise HTTPException(status_code=401, detail="X-User-Id header is required")

    # T2.2: 限流检查
    allowed = await _check_rate_limit(x_user_id)
    if not allowed:
        raise HTTPException(
            status_code=429,
            detail="rate_limit_exceeded",
            headers={"Retry-After": str(SESSION_INIT_RATE_LIMIT_WINDOW)},
        )

    # 复用 session_manager.create_session 写入 Redis SHORT_TERM
    task_id = body.task_id or f"task_{int(time.time())}_{x_user_id[-6:]}"
    try:
        session = await session_manager.create_session(
            user_id=x_user_id,
            task_id=task_id,
        )
    except Exception as e:
        logger.error("Failed to pre-create session for user=%s: %s", x_user_id, e)
        raise HTTPException(status_code=503, detail="session_create_failed") from e

    sid = session["session_id"]
    created_at = session["created_at"]
    ttl = session_manager.SESSION_TTL

    # 计算过期时间（ISO8601）
    created_ts = time.mktime(time.strptime(created_at, "%Y-%m-%dT%H:%M:%SZ"))
    expires_ts = created_ts + ttl
    expires_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(expires_ts))

    # 写入附加元数据（source_port/title）到 session 记录
    if body.source_port or body.title or body.metadata:
        try:
            session["source_port"] = body.source_port
            session["title"] = body.title
            session["metadata"] = body.metadata
            from app.layers.agent_core.memory_orchestrator import memory_orchestrator
            from app.models.memory import MemoryType
            await memory_orchestrator.write(
                x_user_id, MemoryType.SHORT_TERM, sid, session, ttl,
            )
        except Exception as e:
            logger.warning("Failed to enrich session metadata: %s", e)

    logger.info(
        "Session pre-created: user=%s, session=%s, task=%s",
        x_user_id, sid, task_id,
    )

    return SessionCreateResponse(
        code=200,
        data=SessionCreateData(
            session_id=sid,
            task_id=task_id,
            created_at=created_at,
            expires_at=expires_at,
            ttl_seconds=ttl,
        ),
    )


# ---------------------------------------------------------------------------
# T2.4: 历史消息恢复接口
# ---------------------------------------------------------------------------

@router.get("/{session_id}/messages", response_model=SessionMessagesResponse)
async def get_session_messages(
    session_id: str,
    x_user_id: str = Header(default=""),
    limit: int = Query(default=50, ge=1, le=200, description="返回消息数量，最大 200"),
    before_msg_id: str = Query(default="", description="分页游标：返回此 ID 之前的消息"),
) -> SessionMessagesResponse:
    """获取指定 session 的历史消息列表。

    - 数据源：优先 Redis L1 `session:{id}:window`，不可用时降级到 L2。
    - 鉴权：严格按 user_id 隔离，越权访问返回 403 并记录审计日志。
    - 分页：基于 before_msg_id 游标，limit 默认 50、最大 200。
    """
    if not x_user_id:
        raise HTTPException(status_code=401, detail="X-User-Id header is required")

    # 1. 校验 session 归属权（user_id 严格隔离）
    session = await session_manager.get_session(x_user_id, session_id)
    if session is None:
        # 越权或不存在：记录审计日志后返回 404
        await audit_logger.log(
            event_type="session_access_denied",
            user_id=x_user_id,
            session_id=session_id,
            details={"reason": "session_not_found_or_forbidden"},
            severity="WARNING",
        )
        raise HTTPException(status_code=404, detail="session not found")

    # session 的 user_id 必须与请求 user_id 一致
    if session.get("user_id") and session["user_id"] != x_user_id:
        await audit_logger.log(
            event_type="session_access_denied",
            user_id=x_user_id,
            session_id=session_id,
            details={
                "reason": "user_mismatch",
                "session_owner": session.get("user_id", ""),
            },
            severity="WARNING",
        )
        raise HTTPException(status_code=403, detail="access denied")

    # 2. 从 Redis L1 window 读取消息（按时间倒序存储，需反转）
    messages: list[dict[str, Any]] = []
    redis_available = True
    try:
        r = await redis_client.get_redis()
        window_key = SESSION_WINDOW_KEY_PATTERN.format(session_id=session_id)
        raw_items = await r.lrange(window_key, 0, -1)
        for raw in reversed(raw_items):  # 反转为时间正序
            if isinstance(raw, bytes):
                raw = raw.decode("utf-8")
            try:
                d = json.loads(raw)
            except json.JSONDecodeError:
                continue
            messages.append({
                "msg_id": d.get("metadata", {}).get("msg_id", "") or d.get("timestamp", ""),
                "role": d.get("role", "user"),
                "content": d.get("content", ""),
                "timestamp": d.get("timestamp", ""),
                "metadata": d.get("metadata", {}),
            })
    except Exception as e:
        logger.warning("Redis L1 read failed for session=%s: %s", session_id, e)
        redis_available = False

    # 3. Redis 不可用时降级到 WorkingMemory L0 / SHORT_TERM 快照
    if not redis_available or not messages:
        try:
            wm = working_memory_manager.get_session(session_id)
            if wm is None:
                wm = await working_memory_manager.load_from_l1(x_user_id, session_id)
            if wm is not None:
                for idx, msg in enumerate(wm.messages):
                    msg_id = msg.metadata.get("msg_id") or f"{msg.timestamp.isoformat()}_{idx}"
                    messages.append({
                        "msg_id": msg_id,
                        "role": msg.role,
                        "content": msg.content,
                        "timestamp": msg.timestamp.isoformat(),
                        "metadata": msg.metadata,
                    })
        except Exception as e:
            logger.warning("L0/L1 fallback failed for session=%s: %s", session_id, e)

    # 4. 应用 before_msg_id 游标分页
    if before_msg_id:
        try:
            cursor_idx = next(
                i for i, m in enumerate(messages) if m["msg_id"] == before_msg_id
            )
            messages = messages[:cursor_idx]
        except StopIteration:
            # 游标不存在：返回空集，前端应停止翻页
            messages = []

    # 5. 应用 limit
    has_more = len(messages) > limit
    paged = messages[-limit:] if messages else []
    next_before_msg_id = paged[0]["msg_id"] if has_more and paged else None

    # 6. 转换为响应模型
    items = [
        SessionMessageItem(
            msg_id=m["msg_id"],
            role=m["role"],
            content=m["content"],
            timestamp=m["timestamp"],
            metadata=m["metadata"],
        )
        for m in paged
    ]

    return SessionMessagesResponse(
        code=200,
        data=SessionMessagesData(
            session_id=session_id,
            messages=items,
            has_more=has_more,
            next_before_msg_id=next_before_msg_id,
        ),
    )


# ---------------------------------------------------------------------------
# T2.6: Session 过期状态查询
# ---------------------------------------------------------------------------

class SessionExpiryData(BaseModel):
    expired: bool
    expiring_soon: bool
    expires_at: str
    remaining_seconds: int


class SessionExpiryResponse(BaseModel):
    code: int = 200
    data: SessionExpiryData


@router.get("/{session_id}/expiry", response_model=SessionExpiryResponse)
async def get_session_expiry(
    session_id: str,
    x_user_id: str = Header(default=""),
) -> SessionExpiryResponse:
    """查询 session 过期状态，供前端展示过期/即将过期提示。"""
    if not x_user_id:
        raise HTTPException(status_code=401, detail="X-User-Id header is required")

    status = await session_manager.get_expiry_status(x_user_id, session_id)
    return SessionExpiryResponse(
        code=200,
        data=SessionExpiryData(
            expired=status["expired"],
            expiring_soon=status["expiring_soon"],
            expires_at=status["expires_at"],
            remaining_seconds=status["remaining_seconds"],
        ),
    )
