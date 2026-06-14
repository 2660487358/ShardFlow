"""WorkingMemoryManager — 短期记忆管理器 (FR-WM-001 ~ FR-WM-004).

Manages the complete lifecycle of short-term (working) memory:
- Session context maintenance: dialogue history + intent stack (FR-WM-001)
- Token usage monitoring with 80% threshold alert (FR-WM-002)
- LLM-powered context compression (FR-WM-002)
- Session-end archiving to long-term memory (FR-WM-003)
- Working memory data structure (FR-WM-004)

Storage: Python local memory (L0) + Redis (L1) for SHORT_TERM type.
No L2 persistence — ephemeral by design.
"""
import logging
import uuid
from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, Field

from app.layers.agent_core.context_manager import context_manager
from app.layers.agent_core.memory_orchestrator import memory_orchestrator
from app.models.memory import MemoryType

logger = logging.getLogger(__name__)


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
    token_usage: TokenUsage = Field(default_factory=TokenUsage)
    task_id: str = ""
    task_type: str = ""
    is_compressed: bool = False

    model_config = {"extra": "allow"}


# ---------------------------------------------------------------------------
# WorkingMemoryManager
# ---------------------------------------------------------------------------

class WorkingMemoryManager:
    """Manages short-term (working) memory for the current session.

    All operations are in-memory (L0) with optional Redis (L1) sync.
    Short-term memory is never persisted to L2 (Java/PostgreSQL).
    """

    # FR-WM-002: Compression threshold (80% usage)
    COMPRESS_THRESHOLD: float = 0.80
    # Target compression ratio: 20-30% of original
    TARGET_COMPRESS_RATIO: float = 0.25

    def __init__(self) -> None:
        # L0 cache: session_id -> WorkingMemoryData
        self._sessions: dict[str, WorkingMemoryData] = {}

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
        """Add a message to the session's dialogue history."""
        wm = self._sessions.get(session_id)
        if wm is None:
            raise ValueError(f"Session not found: {session_id}")

        msg = MessageItem(role=role, content=content, metadata=metadata or {})
        wm.messages.append(msg)

        # Update token usage
        self._update_token_usage(wm)

        # FR-WM-002: Check if compression is needed
        if wm.token_usage.usage_ratio >= self.COMPRESS_THRESHOLD:
            logger.warning(
                "Context usage %.1f%% exceeds threshold %.0f%% for session %s",
                wm.token_usage.usage_ratio * 100,
                self.COMPRESS_THRESHOLD * 100,
                session_id,
            )

        return msg

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

        Strategy: Keep recent messages (last 4), summarize older ones.
        Target compression ratio: 20-30% of original text.
        """
        wm = self._sessions.get(session_id)
        if wm is None:
            raise ValueError(f"Session not found: {session_id}")

        if len(wm.messages) <= 6:
            logger.info("Session %s has too few messages to compress, skipping", session_id)
            return wm.context_summary

        # Split: messages to summarize vs. keep
        keep_recent = 4
        messages_to_compress = wm.messages[:-keep_recent]
        recent_messages = wm.messages[-keep_recent:]

        if not messages_to_compress:
            return wm.context_summary

        # Build compression prompt
        compression_prompt = self._build_compression_prompt(messages_to_compress, wm.context_summary)

        # Call LLM for compression
        summary = await self._call_llm_compress(compression_prompt)

        # Update working memory
        wm.context_summary = summary
        wm.messages = recent_messages
        wm.is_compressed = True
        self._update_token_usage(wm)

        logger.info(
            "Context compressed for session %s: %d messages -> summary + %d recent messages",
            session_id, len(messages_to_compress), len(recent_messages),
        )

        # Persist compressed state to L1 (Redis)
        await self._persist_to_l1(wm)

        return summary

    def _build_compression_prompt(self, messages: list[MessageItem],
                                  existing_summary: str) -> str:
        """Build the LLM prompt for context compression."""
        conversation_text = "\n".join(
            f"[{m.role}] {m.content[:500]}" for m in messages
        )

        prompt = (
            "请将以下对话历史压缩为简洁的结构化摘要。要求：\n"
            "1. 保留关键实体（人名、地名、时间、数值、技术术语）\n"
            "2. 保留已确认的结论和已排除的方案\n"
            "3. 保留待办事项和未解决问题\n"
            "4. 去除寒暄、重复确认等低信息内容\n"
            "5. 压缩率为原始文本的20-30%\n"
            "6. 输出格式：\n"
            "   - 已确认结论：...\n"
            "   - 已排除方案：...\n"
            "   - 待办事项：...\n"
            "   - 关键实体：...\n"
            "   - 当前意图：...\n"
        )

        if existing_summary:
            prompt += f"\n已有摘要（请在此基础上更新）：\n{existing_summary}\n"

        prompt += f"\n待压缩对话：\n{conversation_text}"

        return prompt

    async def _call_llm_compress(self, prompt: str) -> str:
        """Call LLM to generate a compression summary.

        Uses the ModelClientManager to make the actual LLM call.
        Falls back to a simple truncation if LLM is unavailable.
        """
        try:
            from app.layers.agent_core.model_client_manager import model_client_manager
            from app.layers.agent_core.llm_router import llm_router

            model_id = llm_router.MODEL_MAP.get("compress", "deepseek-chat")
            client, actual_model = await model_client_manager.get_client(model_id)

            payload = {
                "model": actual_model,
                "messages": [
                    {"role": "system", "content": "你是一个对话摘要专家，擅长提取关键信息并压缩冗余内容。"},
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
        """Fallback compression: extract key lines when LLM is unavailable."""
        lines = text.split("\n")
        key_lines = [l for l in lines if any(
            kw in l for kw in ["确认", "排除", "待办", "决定", "结论", "意图"]
        )]
        if not key_lines:
            # Take first 20% of lines as summary
            keep_count = max(1, len(lines) // 5)
            key_lines = lines[:keep_count]
        return "\n".join(key_lines)

    # ------------------------------------------------------------------
    # FR-WM-003: Short-term memory archiving
    # ------------------------------------------------------------------

    async def archive_session(self, session_id: str) -> dict[str, Any]:
        """Archive short-term memory to long-term memory at session end.

        Extraction targets:
        1. Session state summary -> SESSION_SUMMARY (L1 + L2)
        2. User fact information -> SEMANTIC (L0 + L1 + L2)
        3. Key decisions/events -> EPISODIC (L0 + L1 + L2)

        After archiving, the short-term memory is safely discardable.
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
            logger.error("Error during session archiving for %s: %s", session_id, e)
            archive_result["archived"] = False
            archive_result["error"] = str(e)
            return archive_result

        # Clean up L0 after successful archive
        self._sessions.pop(session_id, None)
        logger.info(
            "Session %s archived: summary=%s, semantic=%d, episodic=%d",
            session_id,
            archive_result["summary_archived"],
            archive_result["semantic_extracted"],
            archive_result["episodic_extracted"],
        )

        return archive_result

    def _extract_summary(self, wm: WorkingMemoryData) -> dict[str, Any]:
        """Extract session state summary from working memory."""
        # Build knowledge state from messages and context summary
        confirmed: list[str] = []
        excluded: list[str] = []
        pending: list[str] = []

        # Parse context_summary for structured knowledge
        if wm.context_summary:
            for line in wm.context_summary.split("\n"):
                line = line.strip()
                if line.startswith("- 已确认") or line.startswith("已确认结论"):
                    confirmed.append(line.lstrip("- 已确认结论：").strip())
                elif line.startswith("- 已排除") or line.startswith("已排除方案"):
                    excluded.append(line.lstrip("- 已排除方案：").strip())
                elif line.startswith("- 待办") or line.startswith("待办事项"):
                    pending.append(line.lstrip("- 待办事项：").strip())

        # Collect tools used from messages
        tools_used = list(set(
            m.metadata.get("tool_name", "")
            for m in wm.messages
            if m.metadata.get("tool_name")
        ))

        return {
            "summary_id": f"ss_{uuid.uuid4().hex[:12]}",
            "user_id": wm.user_id,
            "task_id": wm.task_id,
            "session_seq": 1,
            "task_type": wm.task_type,
            "task_goal": wm.intent_stack[0] if wm.intent_stack else "",
            "knowledge_state": {
                "confirmed": confirmed,
                "excluded": excluded,
                "pending": pending,
                "key_decisions": [],
            },
            "user_context": {},
            "execution_state": {
                "completed_steps": len(wm.messages),
                "current_step": wm.intent_stack[-1] if wm.intent_stack else "",
                "tools_used": tools_used,
                "estimated_remaining": "",
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
        path = episodic_memory_manager.start_decision_path(
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

    async def _persist_to_l1(self, wm: WorkingMemoryData) -> None:
        """Persist working memory to Redis (L1) for cross-request access."""
        try:
            await memory_orchestrator.write_session(
                wm.user_id, wm.session_id, wm.model_dump(mode="json")
            )
        except Exception as e:
            logger.warning("Failed to persist working memory to L1: %s", e)

    async def load_from_l1(self, user_id: str, session_id: str) -> WorkingMemoryData | None:
        """Load working memory from Redis (L1) if not in L0."""
        if session_id in self._sessions:
            return self._sessions[session_id]

        try:
            data = await memory_orchestrator.read_session(user_id, session_id)
            if data:
                wm = WorkingMemoryData(**data)
                self._sessions[session_id] = wm
                return wm
        except Exception as e:
            logger.warning("Failed to load working memory from L1: %s", e)

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
