"""WorkingMemoryManager — 短期记忆管理器 (FR-WM-001 ~ FR-WM-004).

Manages the complete lifecycle of short-term (working) memory:
- Session context maintenance: dialogue history + intent stack (FR-WM-001)
- Token usage monitoring with 80% threshold alert (FR-WM-002)
- LLM-powered context compression (FR-WM-002)
- Session-end archiving to long-term memory (FR-WM-003)
- Working memory data structure (FR-WM-004)

Storage: Python local memory (L0) + Redis (L1) for SHORT_TERM type.
No L2 persistence — ephemeral by design.

S3.2: 短期记忆分层落地
- L0: in-memory dict (self._sessions) — sub-ms access
- L1: Redis List `session:{session_id}:window` — Pipeline LPUSH+LTRIM+EXPIRE (C-8.5)
- 主权端: Python 单端写入，Java 禁止读取（C-5.12）
- TTL: 24h（会话生命周期）

阶段3 P1: L2 概念摘要增强
- 增量压缩：溢出消息数 >= memory_compress_batch 时触发（T3.1/T3.2）
- 校正压缩：每 memory_corrective_compress_interval 轮触发一次（T3.3）
- 压缩异步执行，不阻塞首 token（AC-16）
- 使用 app/prompts/memory_compress_prompt.py 版本化模板（T3.4）
"""
import asyncio
import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, Field

from app.layers.agent_core.context_manager import context_manager
from app.layers.agent_core.memory_orchestrator import memory_orchestrator
from app.models.memory import MemoryType
from app.prompts.memory_compress_prompt import (
    build_corrective_prompt,
    build_incremental_prompt,
    parse_compress_response,
)

logger = logging.getLogger(__name__)

# S3.2: Redis window constants per Redis-Key规范文档 §3.1
SESSION_WINDOW_TTL_SECONDS = 86400  # 24h — session lifecycle
SESSION_WINDOW_KEY_PATTERN = "session:{session_id}:window"


# ---------------------------------------------------------------------------
# FR-WM-004: Short-term memory data structure
# ---------------------------------------------------------------------------

class MessageItem(BaseModel):
    """A single message in the working memory."""
    role: str                              # user | assistant | system | tool
    content: str = ""
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    metadata: dict[str, Any] = Field(default_factory=dict)


class TokenUsage(BaseModel):
    """Token usage tracking for a session."""
    current: int = 0
    limit: int = 128000
    usage_ratio: float = 0.0


class StructuredSummary(BaseModel):
    """FR-WM-004: Structured version of concept summary (子层B).

    Maintained alongside context_summary for direct use in snapshot assembly.
    阶段3 P1: 新增 entities / intent 字段，对齐 memory_compress_prompt 输出。
    """
    confirmed: list[str] = Field(default_factory=list)
    excluded: list[str] = Field(default_factory=list)
    pending: list[str] = Field(default_factory=list)
    entities: list[str] = Field(default_factory=list)
    intent: str = ""


class WorkingMemoryData(BaseModel):
    """FR-WM-004: Complete working memory data structure.

    Stored as the payload of a SHORT_TERM memory record.
    """
    session_id: str = ""
    user_id: str = ""
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    messages: list[MessageItem] = Field(default_factory=list)
    intent_stack: list[str] = Field(default_factory=list)
    context_summary: str = ""
    structured_summary: StructuredSummary = Field(default_factory=StructuredSummary)
    token_usage: TokenUsage = Field(default_factory=TokenUsage)
    task_id: str = ""
    task_type: str = ""
    is_compressed: bool = False
    compress_round_count: int = 0

    model_config = {"extra": "allow"}


# ---------------------------------------------------------------------------
# WorkingMemoryManager
# ---------------------------------------------------------------------------

class WorkingMemoryManager:
    """Manages short-term (working) memory for the current session.

    All operations are in-memory (L0) with optional Redis (L1) sync.
    Short-term memory is never persisted to L2 (Java/PostgreSQL).
    """

    @property
    def COMPRESS_THRESHOLD(self) -> float:
        from app.config import settings
        return settings.memory_compress_threshold

    @property
    def TARGET_COMPRESS_RATIO(self) -> float:
        from app.config import settings
        return settings.memory_target_compress_ratio

    @property
    def COMPRESS_BATCH(self) -> int:
        """T3.1: 溢出批量压缩阈值，默认 4。"""
        from app.config import settings
        return getattr(settings, "memory_compress_batch", 4)

    @property
    def COMPRESS_ASYNC(self) -> bool:
        """T3.1: 压缩异步执行开关，默认 True。"""
        from app.config import settings
        return getattr(settings, "memory_compress_async", True)

    def __init__(self) -> None:
        # L0 cache: session_id -> WorkingMemoryData
        self._sessions: dict[str, WorkingMemoryData] = {}
        # T3.1: 会话级压缩锁，保证同一 session 串行压缩，避免竞态
        self._compress_locks: dict[str, asyncio.Lock] = {}
        # T3.1: 正在压缩的 session 集合，防止重复触发
        self._compressing: set[str] = set()

    # ------------------------------------------------------------------
    # T5.1: 事件循环安全调度工具
    # ------------------------------------------------------------------

    @staticmethod
    def _safe_schedule(coro: Any, *, tag: str = "") -> None:
        """T5.1: 安全调度协程，无运行中事件循环时静默跳过。

        解决 asyncio.ensure_future 在无事件循环时的 DeprecationWarning。
        fire-and-forget 语义：L1 推送/压缩均为非关键路径，无循环时跳过不影响主流程。

        Args:
            coro: 待调度的协程对象
            tag: 日志标签（如 "L1 push" / "compress"），便于排查
        """
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(coro)
        except RuntimeError:
            # 无运行中事件循环（同步上下文），fire-and-forget 跳过
            logger.debug("No running event loop, skip %s scheduling", tag or "async task")
            # 关闭未调度的协程，避免 "coroutine was never awaited" 告警
            coro.close()

    # ------------------------------------------------------------------
    # FR-WM-001: Session context maintenance
    # ------------------------------------------------------------------

    def create_session(self, user_id: str, session_id: str | None = None,
                       task_id: str = "", task_type: str = "") -> WorkingMemoryData:
        """Create a new working memory session."""
        if session_id is None:
            session_id = f"sess_{uuid.uuid4().hex[:12]}"

        wm = WorkingMemoryData(
            session_id=session_id,
            user_id=user_id,
            task_id=task_id,
            task_type=task_type,
            token_usage=TokenUsage(limit=context_manager._usable_tokens()),
        )
        self._sessions[session_id] = wm
        logger.info("Working memory session created: session_id=%s, user_id=%s", session_id, user_id)
        return wm

    def get_session(self, session_id: str) -> WorkingMemoryData | None:
        """Get working memory data for a session."""
        return self._sessions.get(session_id)

    def add_message(self, session_id: str, role: str, content: str,
                    metadata: dict[str, Any] | None = None) -> MessageItem:
        """Add a message to the session's dialogue history.

        阶段3 P1 (T3.1): 当消息数超过窗口大小且溢出量达到 batch 阈值时，
        异步触发增量压缩，不阻塞用户首 token (AC-16)。
        """
        wm = self._sessions.get(session_id)
        if wm is None:
            raise ValueError(f"Session not found: {session_id}")

        msg = MessageItem(role=role, content=content, metadata=metadata or {})
        wm.messages.append(msg)

        # Update token usage
        self._update_token_usage(wm)

        # S3.2: Push to Redis L1 window (Pipeline LPUSH+LTRIM+EXPIRE, fire-and-forget)
        # T5.1: 使用 _safe_schedule 替代 asyncio.ensure_future，避免无事件循环时的告警
        self._safe_schedule(
            self._push_to_window_l1(session_id, msg),
            tag="L1 push",
        )

        # FR-WM-002: Check if token-based compression is needed (warning only)
        if wm.token_usage.usage_ratio >= self.COMPRESS_THRESHOLD:
            logger.warning(
                "Context usage %.1f%% exceeds threshold %.0f%% for session %s",
                wm.token_usage.usage_ratio * 100,
                self.COMPRESS_THRESHOLD * 100,
                session_id,
            )

        # T3.1: 消息数触发增量压缩（溢出量 >= batch 时触发）
        self._maybe_trigger_compress(session_id, wm)

        return msg

    # ------------------------------------------------------------------
    # T3.1: 增量压缩触发逻辑
    # ------------------------------------------------------------------

    def _maybe_trigger_compress(self, session_id: str, wm: WorkingMemoryData) -> None:
        """T3.1: 检查是否需要触发增量压缩.

        触发条件：
        1. 消息数 > memory_window_size（窗口溢出）
        2. 溢出量 >= memory_compress_batch（达到批量阈值）
        3. 当前 session 未在压缩中（避免重复触发）

        压缩异步执行，不阻塞 add_message 返回（AC-16）。
        """
        from app.config import settings
        window_size = settings.memory_window_size
        overflow = len(wm.messages) - window_size
        if overflow < self.COMPRESS_BATCH:
            return
        if session_id in self._compressing:
            logger.debug("Session %s already compressing, skip trigger", session_id)
            return

        if self.COMPRESS_ASYNC:
            # T3.1 + T5.1: 异步触发压缩，不阻塞首 token；使用 _safe_schedule 避免无事件循环告警
            self._safe_schedule(
                self._async_compress_wrapper(session_id),
                tag="compress",
            )
            logger.info(
                "Triggered async compress for session %s: messages=%d, overflow=%d, batch=%d",
                session_id, len(wm.messages), overflow, self.COMPRESS_BATCH,
            )
        else:
            # 同步模式：仅标记需要压缩，由调用方显式调用 compress_context
            logger.debug("Async compress disabled, marked session %s for compression", session_id)

    async def _async_compress_wrapper(self, session_id: str) -> None:
        """T3.1: 异步压缩包装器，保证同一 session 串行执行.

        使用会话级锁避免竞态（风险：压缩异步执行引入竞态）。
        压缩失败时降级为硬窗口，不阻塞对话（AC-16 降级策略）。
        """
        if session_id in self._compressing:
            return
        self._compressing.add(session_id)
        lock = self._compress_locks.setdefault(session_id, asyncio.Lock())
        try:
            async with lock:
                await self.compress_context(session_id)
        except Exception as e:
            logger.error(
                "Async compress failed for session %s, degrading to hard window: %s",
                session_id, e,
            )
        finally:
            self._compressing.discard(session_id)

    def push_intent(self, session_id: str, intent: str) -> None:
        """Push an intent onto the session's intent stack."""
        wm = self._sessions.get(session_id)
        if wm is None:
            raise ValueError(f"Session not found: {session_id}")
        wm.intent_stack.append(intent)

    def pop_intent(self, session_id: str) -> str | None:
        """Pop the top intent from the session's intent stack."""
        wm = self._sessions.get(session_id)
        if wm is None:
            raise ValueError(f"Session not found: {session_id}")
        return wm.intent_stack.pop() if wm.intent_stack else None

    def get_current_intent(self, session_id: str) -> str | None:
        """Get the current (top) intent without removing it."""
        wm = self._sessions.get(session_id)
        if wm is None:
            return None
        return wm.intent_stack[-1] if wm.intent_stack else None

    def get_messages(self, session_id: str) -> list[MessageItem]:
        """Get all messages for a session."""
        wm = self._sessions.get(session_id)
        if wm is None:
            return []
        return wm.messages

    def get_messages_as_dicts(self, session_id: str) -> list[dict[str, Any]]:
        """Get messages in the format suitable for LLM API calls."""
        wm = self._sessions.get(session_id)
        if wm is None:
            return []
        return [{"role": m.role, "content": m.content} for m in wm.messages]

    # ------------------------------------------------------------------
    # FR-WM-002: Context capacity monitoring
    # ------------------------------------------------------------------

    def _update_token_usage(self, wm: WorkingMemoryData) -> None:
        """Recalculate token usage for the working memory."""
        messages_dicts = [{"role": m.role, "content": m.content} for m in wm.messages]
        estimated = context_manager.estimate_tokens(messages_dicts)
        wm.token_usage.current = estimated
        usable = context_manager._usable_tokens()
        wm.token_usage.limit = usable
        wm.token_usage.usage_ratio = min(estimated / usable, 1.0) if usable > 0 else 1.0

    def get_token_usage(self, session_id: str) -> TokenUsage | None:
        """Get current token usage for a session."""
        wm = self._sessions.get(session_id)
        if wm is None:
            return None
        self._update_token_usage(wm)
        return wm.token_usage

    def should_compress(self, session_id: str) -> bool:
        """Check if the session context should be compressed."""
        wm = self._sessions.get(session_id)
        if wm is None:
            return False
        self._update_token_usage(wm)
        return wm.token_usage.usage_ratio >= self.COMPRESS_THRESHOLD

    # ------------------------------------------------------------------
    # FR-WM-002: LLM compression summary
    # ------------------------------------------------------------------

    async def compress_context(self, session_id: str) -> str:
        """Compress the session context using LLM summarization.

        阶段3 P1 (T3.2/T3.3): 增量压缩 + 校正压缩
        - 增量压缩：溢出消息 + 已有摘要 → 更新后的双版本摘要
        - 校正压缩：每 memory_corrective_compress_interval 轮触发一次，
          将当前窗口 + 已有摘要一起过 LLM，防止增量误差累积

        策略：保留最近 memory_window_size 条消息，压缩更早的消息。
        目标压缩率：20-30%。

        AC-16: 压缩异步执行（由 _async_compress_wrapper 调用），不阻塞首 token。
        AC-18: 每 20 轮自动执行校正压缩。
        """
        wm = self._sessions.get(session_id)
        if wm is None:
            raise ValueError(f"Session not found: {session_id}")

        from app.config import settings
        keep_recent = settings.memory_window_size

        # 消息数不足，跳过压缩
        if len(wm.messages) <= keep_recent:
            logger.info(
                "Session %s has too few messages to compress (messages=%d, window=%d), skipping",
                session_id, len(wm.messages), keep_recent,
            )
            return wm.context_summary

        # Split: messages to summarize vs. keep
        messages_to_compress = wm.messages[:-keep_recent]
        recent_messages = wm.messages[-keep_recent:]

        if not messages_to_compress:
            return wm.context_summary

        # T3.3: 校正压缩判断 — 每 K 轮触发一次（K 默认 20）
        corrective_interval = self._get_corrective_interval()
        should_corrective = (
            wm.compress_round_count > 0
            and wm.compress_round_count % corrective_interval == 0
        )

        if should_corrective:
            # T3.3: 校正压缩 — 当前窗口 + 已有摘要一起过 LLM
            compress_result = await self._corrective_compress(wm, recent_messages)
        else:
            # T3.2: 增量压缩 — 溢出消息 + 已有摘要
            compress_result = await self._incremental_compress(
                messages_to_compress, wm.context_summary,
            )

        # 更新 working memory
        wm.context_summary = compress_result["natural_summary"]
        wm.structured_summary = self._build_structured_summary(compress_result["structured_summary"])
        wm.messages = recent_messages
        wm.is_compressed = True
        wm.compress_round_count += 1
        self._update_token_usage(wm)

        logger.info(
            "Context compressed for session %s: %d messages -> summary + %d recent messages "
            "(round=%d, corrective=%s)",
            session_id, len(messages_to_compress), len(recent_messages),
            wm.compress_round_count, should_corrective,
        )

        # 持久化压缩后的状态到 L1 (Redis)
        await self._persist_to_l1(wm)

        return wm.context_summary

    async def _incremental_compress(
        self,
        messages_to_compress: list[MessageItem],
        existing_summary: str,
    ) -> dict[str, Any]:
        """T3.2: 增量压缩 — 调用 LLM 生成自然语言摘要 + 结构化摘要 JSON.

        输入：已有摘要 + 新增溢出消息
        输出：{"natural_summary": str, "structured_summary": dict}
        压缩失败时降级为硬窗口截断（AC-16 降级策略）。
        """
        prompt = build_incremental_prompt(messages_to_compress, existing_summary)
        llm_output = await self._call_llm_compress(prompt)
        return parse_compress_response(llm_output)

    def _build_structured_summary(self, data: dict[str, Any]) -> StructuredSummary:
        """T3.2: 从解析后的字典构建 StructuredSummary 模型."""
        return StructuredSummary(
            confirmed=list(data.get("confirmed", [])),
            excluded=list(data.get("excluded", [])),
            pending=list(data.get("pending", [])),
            entities=list(data.get("entities", [])),
            intent=str(data.get("intent", "")),
        )

    def _build_compression_prompt(self, messages: list[MessageItem],
                                  existing_summary: str) -> str:
        """Build the LLM prompt for context compression (兼容旧调用，使用新模板)."""
        return build_incremental_prompt(messages, existing_summary)

    async def _call_llm_compress(self, prompt: str) -> str:
        """Call LLM to generate a compression summary.

        Uses the ModelClientManager to make the actual LLM call.
        Falls back to a simple truncation if LLM is unavailable (AC-16 降级).
        """
        try:
            from app.layers.agent_core.llm_router import llm_router
            from app.layers.agent_core.model_client_manager import model_client_manager
            from app.prompts.memory_compress_prompt import SYSTEM_ROLE

            model_id = llm_router.MODEL_MAP.get("compress", "deepseek-chat")
            client, actual_model = await model_client_manager.get_client(model_id)

            payload = {
                "model": actual_model,
                "messages": [
                    {"role": "system", "content": SYSTEM_ROLE},
                    {"role": "user", "content": prompt},
                ],
                "max_tokens": 1024,
                "temperature": 0.3,
            }

            resp = await client.post("/chat/completions", json=payload, timeout=15.0)
            resp.raise_for_status()
            data = resp.json()

            choices = data.get("choices", [])
            if choices:
                return choices[0].get("message", {}).get("content", "")

        except Exception as e:
            logger.warning("LLM compression failed, using fallback truncation: %s", e)

        # Fallback: simple truncation
        return self._fallback_compress(prompt)

    def _fallback_compress(self, text: str) -> str:
        """Fallback compression: extract key lines when LLM is unavailable.

        返回旧式文本格式，由 parse_compress_response 的兜底解析器处理。
        """
        lines = text.split("\n")
        key_lines = [line for line in lines if any(
            kw in line for kw in ["确认", "排除", "待办", "决定", "结论", "意图", "实体"]
        )]
        if not key_lines:
            # Take first 20% of lines as summary
            keep_count = max(1, len(lines) // 5)
            key_lines = lines[:keep_count]
        return "\n".join(key_lines)

    def _parse_structured_summary(self, summary_text: str) -> StructuredSummary:
        """Parse a text summary into a StructuredSummary model (兼容旧调用).

        阶段3 P1: 委托给 memory_compress_prompt.parse_compress_response，
        支持新 JSON 格式和旧文本格式。
        """
        result = parse_compress_response(summary_text)
        return self._build_structured_summary(result["structured_summary"])

    # ------------------------------------------------------------------
    # T3.3: Corrective compression
    # ------------------------------------------------------------------

    def _get_corrective_interval(self) -> int:
        """Get the corrective compression interval from config, default 20."""
        try:
            from app.config import settings
            return getattr(settings, "memory_corrective_compress_interval", 20)
        except Exception:
            return 20

    async def _corrective_compress(
        self, wm: WorkingMemoryData, recent_messages: list[MessageItem],
    ) -> dict[str, Any]:
        """T3.3: 校正压缩 — 将当前窗口 + 已有概念摘要一起过 LLM.

        产出校正后双版本替代累积版本，防止增量误差累积。
        校正压缩后 compress_round_count 不重置，继续累加。

        Returns:
            {"natural_summary": str, "structured_summary": dict}
        """
        prompt = build_corrective_prompt(recent_messages, wm.context_summary)
        llm_output = await self._call_llm_compress(prompt)
        result = parse_compress_response(llm_output)

        logger.info(
            "Corrective compression applied for session %s (round=%d)",
            wm.session_id, wm.compress_round_count,
        )

        return result

    # ------------------------------------------------------------------
    # FR-WM-003: Short-term memory archiving
    # ------------------------------------------------------------------

    async def archive_session(self, session_id: str) -> dict[str, Any]:
        """Archive short-term memory to long-term memory at session end.

        Extraction targets:
        1. Session state summary -> SESSION_SUMMARY (L1 + L2)
        2. User fact information -> SEMANTIC (L0 + L1 + L2)
        3. Key decisions/events -> EPISODIC (L0 + L1 + L2)

        修正：归档后保留短期记忆（L0 + L1），不立即删除。
        短期记忆依赖 TTL（24h）自然过期，确保跨轮对话不丢失上下文。
        仅清理 dedicated window List，因为消息已转为 episodic chunk 存储。
        """
        wm = self._sessions.get(session_id)
        if wm is None:
            logger.warning("Cannot archive non-existent session: %s", session_id)
            return {"archived": False, "reason": "session_not_found"}

        archive_result: dict[str, Any] = {
            "archived": True,
            "session_id": session_id,
            "user_id": wm.user_id,
            "summary_archived": False,
            "semantic_extracted": 0,
            "episodic_extracted": 0,
        }

        try:
            # 1. Extract and save session state summary
            if wm.task_id:
                summary_data = self._extract_summary(wm)
                await memory_orchestrator.write_summary(
                    wm.user_id, wm.task_id, summary_data
                )
                archive_result["summary_archived"] = True
                logger.info("Session state summary archived for task %s", wm.task_id)

            # 2. Extract semantic memory (user facts)
            semantic_items = await self._extract_semantic(wm)
            for key, data in semantic_items:
                await memory_orchestrator.write_semantic(wm.user_id, key, data)
            archive_result["semantic_extracted"] = len(semantic_items)

            # 3. Extract episodic memory (key decisions/events)
            episodic_items = await self._extract_episodic(wm)
            for key, data in episodic_items:
                await memory_orchestrator.write_episodic(wm.user_id, key, data)
            archive_result["episodic_extracted"] = len(episodic_items)

        except Exception as e:
            import traceback
            logger.error(
                "Error during session archiving for %s: %s\n%s",
                session_id, e, traceback.format_exc()
            )
            archive_result["archived"] = False
            archive_result["error"] = str(e)
            return archive_result

        # 修正：归档后保留 L0 短期记忆，不立即 pop
        # 原代码 self._sessions.pop(session_id, None) 导致同一 session 后续请求丢失历史
        # 短期记忆依赖 TTL（24h）自然过期，同时通过 L1 快照确保跨请求可用

        # 修正：归档后不清理 Redis SHORT_TERM 数据，依赖 24h TTL 自然过期
        # 原代码 memory_orchestrator.delete(SHORT_TERM) 导致 L1 快照丢失
        # 只清理 dedicated window List（消息已归档为 episodic chunk）

        # S3.2: Clean up the dedicated window List (session:{id}:window)
        # Window List 中的原始消息已转换为 episodic chunk，可安全清理
        await self._clear_window_l1(session_id)

        logger.info(
            "Session %s archived: summary=%s, semantic=%d, episodic=%d "
            "(working memory retained for cross-request continuity)",
            session_id,
            archive_result["summary_archived"],
            archive_result["semantic_extracted"],
            archive_result["episodic_extracted"],
        )

        return archive_result

    def _extract_summary(self, wm: WorkingMemoryData) -> dict[str, Any]:
        """Extract session state summary from working memory.

        Per spec 6.2: compressed_history = context_summary (子层A),
        knowledge_state = structured_summary + key_decisions from current window.
        """
        # Use structured_summary directly (already maintained during compression)
        confirmed = list(wm.structured_summary.confirmed)
        excluded = list(wm.structured_summary.excluded)
        pending = list(wm.structured_summary.pending)

        # Also parse context_summary for any additional items not in structured version
        if wm.context_summary:
            for line in wm.context_summary.split("\n"):
                line = line.strip()
                if line.startswith("- 已确认") or line.startswith("已确认结论"):
                    item = line.lstrip("- 已确认结论：").strip()
                    if item and item not in confirmed:
                        confirmed.append(item)
                elif line.startswith("- 已排除") or line.startswith("已排除方案"):
                    item = line.lstrip("- 已排除方案：").strip()
                    if item and item not in excluded:
                        excluded.append(item)
                elif line.startswith("- 待办") or line.startswith("待办事项"):
                    item = line.lstrip("- 待办事项：").strip()
                    if item and item not in pending:
                        pending.append(item)

        # Collect tools used from messages
        tools_used = list(set(
            m.metadata.get("tool_name", "")
            for m in wm.messages
            if m.metadata.get("tool_name")
        ))

        # Estimate remaining progress from intent stack
        estimated_remaining = ""
        if wm.intent_stack:
            estimated_remaining = "50%"
        if not wm.intent_stack and len(wm.messages) > 4:
            estimated_remaining = "90%"

        return {
            "summary_id": f"ss_{uuid.uuid4().hex[:12]}",
            "user_id": wm.user_id,
            "task_id": wm.task_id,
            "session_seq": 1,
            "task_type": wm.task_type,
            "task_goal": wm.intent_stack[0] if wm.intent_stack else "",
            "compressed_history": wm.context_summary,
            "knowledge_state": {
                "confirmed": confirmed,
                "excluded": excluded,
                "pending": pending,
                "key_decisions": [],
                # 阶段3 P1: 新增 entities 和 intent 字段
                "entities": list(wm.structured_summary.entities),
                "intent": wm.structured_summary.intent,
            },
            "user_context": {},
            "execution_state": {
                "completed_steps": len(wm.messages),
                "current_step": wm.intent_stack[-1] if wm.intent_stack else "",
                "tools_used": tools_used,
                "estimated_remaining": estimated_remaining,
            },
            "source_preference": {},
            "version": 1,
        }

    async def _extract_semantic(self, wm: WorkingMemoryData) -> list[tuple[str, dict[str, Any]]]:
        """Extract semantic memory items (user facts) from working memory.

        Delegates to SemanticMemoryManager (P3) for full extraction with
        confidence evaluation and NER support.
        """
        from app.layers.agent_core.semantic_memory_manager import semantic_memory_manager

        messages = [{"role": m.role, "content": m.content} for m in wm.messages]
        result = await semantic_memory_manager.extract_from_messages(
            wm.user_id, messages, wm.session_id,
        )

        # Convert ExtractedFact list to (key, data) tuples for orchestrator
        items: list[tuple[str, dict[str, Any]]] = []
        for fact in result.facts:
            key = f"sem_{uuid.uuid4().hex[:8]}"
            items.append((key, {
                "text": fact.text,
                "category": fact.category,
                "confidence": fact.confidence,
                "source": fact.source,
                "session_id": fact.session_id,
                "structured": fact.structured,
            }))

        # Evolve user profile with new facts
        if result.facts:
            try:
                from app.layers.agent_core.user_profile_manager import user_profile_manager
                await user_profile_manager.evolve_profile(wm.user_id)
            except Exception as e:
                logger.warning("Failed to evolve profile after semantic extraction: %s", e)

        return items

    async def _extract_episodic(self, wm: WorkingMemoryData) -> list[tuple[str, dict[str, Any]]]:
        """Extract episodic memory items (key decisions/events) from working memory.

        Delegates to EpisodicMemoryManager (P4) for full decision-path recording
        with structured step extraction and audit logging.
        """
        from app.layers.agent_core.episodic_memory_manager import episodic_memory_manager

        items: list[tuple[str, dict[str, Any]]] = []

        # Build a decision path from the working memory messages
        episodic_memory_manager.start_decision_path(
            user_id=wm.user_id,
            session_id=wm.session_id,
            task_id=wm.task_id,
            task_type=wm.task_type,
        )

        # Replay messages as decision steps
        for msg in wm.messages:
            if msg.role == "user" and msg == wm.messages[0]:
                # First user message = input
                episodic_memory_manager.record_intent(
                    session_id=wm.session_id,
                    intent=msg.content[:200],
                    confidence=0.8,
                )
            elif msg.role == "tool" or msg.metadata.get("tool_name"):
                # Tool call step
                episodic_memory_manager.record_tool_call(
                    session_id=wm.session_id,
                    tool_name=msg.metadata.get("tool_name", "unknown"),
                    tool_input=msg.metadata.get("tool_input", {}),
                    tool_output=msg.content[:500],
                )
            elif msg.role == "assistant" and msg == wm.messages[-1]:
                # Last assistant message = final output
                episodic_memory_manager.record_final_output(
                    session_id=wm.session_id,
                    output=msg.content[:500],
                    success=True,
                )
            elif msg.role == "assistant":
                # Intermediate conclusion
                episodic_memory_manager.record_intermediate_conclusion(
                    session_id=wm.session_id,
                    conclusion=msg.content[:200],
                    confidence=0.7,
                )

        # Save the complete decision path
        saved_data = await episodic_memory_manager.complete_and_save_decision_path(
            session_id=wm.session_id,
        )

        if saved_data:
            key = saved_data.get("path_id", f"ep_{uuid.uuid4().hex[:8]}")
            items.append((key, saved_data))

        # Also save individual decision events as separate chunks for granular retrieval
        for msg in wm.messages:
            if msg.role == "tool" or msg.metadata.get("tool_name"):
                key = f"ep_{uuid.uuid4().hex[:8]}"
                items.append((key, {
                    "text": f"Tool call: {msg.metadata.get('tool_name', 'unknown')} - {msg.content[:200]}",
                    "source": "conversation",
                    "confidence": 0.8,
                    "session_id": wm.session_id,
                    "category": "decision",
                }))

        return items

    # ------------------------------------------------------------------
    # Persistence helpers
    # ------------------------------------------------------------------

    def _window_key(self, session_id: str) -> str:
        """Build the Redis List key for the session window (S3.2 / Redis-Key规范 §3.1)."""
        return SESSION_WINDOW_KEY_PATTERN.format(session_id=session_id)

    def _window_max_size(self) -> int:
        """Get the window max size from settings (default 50, kept as 2x for LTRIM)."""
        try:
            from app.config import settings
            window_size = getattr(settings, "memory_window_size", 25)
            return max(window_size * 2 - 1, 9)  # C-8.5: WINDOW_SIZE*2-1, min 9
        except Exception:
            return 49

    async def _push_to_window_l1(self, session_id: str, msg: MessageItem) -> None:
        """S3.2: Push a message to the Redis List window using Pipeline.

        Per Redis-Key规范文档 §3.1 operation spec (C-8.5):
            Pipeline: LPUSH + LTRIM(0, WINDOW_SIZE*2-1) + EXPIRE(24h)
        Sovereignty: Python single-end write; Java is forbidden to read (C-5.12).
        """
        try:
            from app.infrastructure.redis_client import redis_client
            r = await redis_client.get_redis()
            key = self._window_key(session_id)
            payload = json.dumps({
                "role": msg.role,
                "content": msg.content,
                "timestamp": msg.timestamp.isoformat(),
                "metadata": msg.metadata,
            }, ensure_ascii=False).encode("utf-8")

            pipe = r.pipeline(transaction=False)
            pipe.lpush(key, payload)
            pipe.ltrim(key, 0, self._window_max_size())
            pipe.expire(key, SESSION_WINDOW_TTL_SECONDS)
            await pipe.execute()
        except Exception as e:
            logger.debug("Failed to push message to window L1: %s", e)

    async def _load_window_l1(self, session_id: str) -> list[MessageItem]:
        """S3.2: Load the message window from Redis List (L1).

        Returns messages in chronological order (oldest first).
        Used when L0 cache miss to restore session context.
        """
        try:
            from app.infrastructure.redis_client import redis_client
            r = await redis_client.get_redis()
            key = self._window_key(session_id)
            # LRANGE 0 -1 returns all items; Redis List is LPUSH-newest-first, reverse for chronology
            raw_items = await r.lrange(key, 0, -1)
            items: list[MessageItem] = []
            for raw in reversed(raw_items):  # reverse to get chronological order
                if isinstance(raw, bytes):
                    raw = raw.decode("utf-8")
                d = json.loads(raw)
                items.append(MessageItem(
                    role=d.get("role", "user"),
                    content=d.get("content", ""),
                    timestamp=(
                    datetime.fromisoformat(d["timestamp"])
                    if d.get("timestamp")
                    else datetime.now(timezone.utc)
                ),
                    metadata=d.get("metadata", {}),
                ))
            return items
        except Exception as e:
            logger.warning("Failed to load window L1 for session %s: %s", session_id, e)
            return []

    async def _clear_window_l1(self, session_id: str) -> None:
        """S3.2: Clear the Redis List window after session archive."""
        try:
            from app.infrastructure.redis_client import redis_client
            r = await redis_client.get_redis()
            await r.delete(self._window_key(session_id))
        except Exception as e:
            logger.debug("Failed to clear window L1: %s", e)

    async def _persist_to_l1(self, wm: WorkingMemoryData) -> None:
        """Persist working memory to Redis (L1) for cross-request access."""
        try:
            await memory_orchestrator.write_session(
                wm.user_id, wm.session_id, wm.model_dump(mode="json")
            )
        except Exception as e:
            logger.warning("Failed to persist working memory to L1: %s", e)

    async def load_from_l1(self, user_id: str, session_id: str) -> WorkingMemoryData | None:
        """Load working memory from Redis (L1) if not in L0.

        Prefers the SHORT_TERM memory record snapshot because it is written
        synchronously by _persist_to_l1 and therefore more complete than the
        fire-and-forget window list. The dedicated window List (session:{id}:window)
        is used as a fallback when the snapshot is missing.
        """
        if session_id in self._sessions:
            return self._sessions[session_id]

        # 1) Prefer the SHORT_TERM memory record snapshot — written synchronously
        # by _persist_to_l1, so it is the authoritative L1 copy of the working memory.
        try:
            data = await memory_orchestrator.read_session(user_id, session_id)
            if data:
                wm = WorkingMemoryData(**data)
                self._update_token_usage(wm)
                self._sessions[session_id] = wm
                logger.info(
                    "Loaded working memory from SHORT_TERM snapshot: session=%s, messages=%d",
                    session_id, len(wm.messages),
                )
                return wm
        except Exception as e:
            logger.warning("Failed to load working memory from SHORT_TERM snapshot: %s", e)

        # 2) Fallback: dedicated window List (S3.2)
        window_messages = await self._load_window_l1(session_id)
        if window_messages:
            wm = WorkingMemoryData(
                session_id=session_id,
                user_id=user_id,
                messages=window_messages,
            )
            self._update_token_usage(wm)
            self._sessions[session_id] = wm
            logger.info(
                "Loaded working memory from window L1: session=%s, messages=%d",
                session_id, len(window_messages),
            )
            return wm

        # 3) L2 fallback: rebuild from archived episodic/summary data
        # When L1 has been cleaned (e.g. after a prior archive_session), try to
        # reconstruct working memory state from L2 so cross-request context is
        # not lost. Uses session_summary and episodic chunks keyed by session_id.
        try:
            from app.layers.agent_core.episodic_memory_manager import episodic_memory_manager
            from app.layers.agent_core.session_state_summary_manager import session_state_summary_manager

            # Try to load the decision path for this session
            dp_data = await memory_orchestrator.read_episodic(user_id, session_id)
            if dp_data is None:
                # Try with dp_ prefix (decision path key format)
                for prefix in ("dp_", ""):
                    candidate_key = f"{prefix}{session_id}" if prefix else session_id
                    dp_data = await memory_orchestrator.read_episodic(user_id, candidate_key)
                    if dp_data:
                        break

            # Try to load the latest session summary for the task
            summary_data = None
            if dp_data and dp_data.get("task_id"):
                summary_data = await session_state_summary_manager.load_latest_summary(
                    user_id, dp_data["task_id"],
                )

            # Reconstruct working memory from archived data
            if dp_data:
                messages: list[dict[str, Any]] = []
                steps = dp_data.get("steps", [])
                for step in steps:
                    if not isinstance(step, dict):
                        continue
                    step_type = step.get("step_type", "")
                    content = step.get("content", "")
                    if step_type == "input" and content:
                        messages.append({"role": "user", "content": content})
                    elif step_type in ("output", "intermediate") and content:
                        messages.append({"role": "assistant", "content": content})

                context_summary = ""
                if summary_data:
                    context_summary = summary_data.compressed_history or ""

                wm = WorkingMemoryData(
                    session_id=session_id,
                    user_id=user_id,
                    messages=[MessageItem(role=m["role"], content=m["content"]) for m in messages],
                    context_summary=context_summary,
                    task_id=dp_data.get("task_id", ""),
                    task_type=dp_data.get("task_type", ""),
                )
                self._update_token_usage(wm)
                self._sessions[session_id] = wm
                # Re-persist to L1 for fast access on subsequent requests
                await self._persist_to_l1(wm)
                return wm
        except Exception as e:
            logger.debug("L2 fallback load failed for session %s: %s", session_id, e)

        return None

    # ------------------------------------------------------------------
    # Session lifecycle
    # ------------------------------------------------------------------

    def end_session(self, session_id: str) -> None:
        """Mark session as ended (L0 cleanup, caller should archive first)."""
        self._sessions.pop(session_id, None)
        logger.info("Working memory session ended: %s", session_id)

    def list_active_sessions(self, user_id: str) -> list[str]:
        """List all active session IDs for a user."""
        return [
            sid for sid, wm in self._sessions.items()
            if wm.user_id == user_id
        ]


# Global singleton
working_memory_manager = WorkingMemoryManager()
