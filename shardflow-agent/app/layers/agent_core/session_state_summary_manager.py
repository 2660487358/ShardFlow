"""SessionStateSummaryManager — 会话状态摘要管理器 (FR-SS-001 ~ FR-SS-004).

Manages the lifecycle of session state summaries:
- Automatic summary extraction (FR-SS-001)
- Summary injection into new sessions (FR-SS-002)
- Cross-port session continuation (FR-SS-003)
- Summary version management (FR-SS-004)

Storage: Redis (L1) + PostgreSQL via Java API (L2).
"""
import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Any

from app.layers.agent_core.memory_orchestrator import memory_orchestrator
from app.models.memory import MemoryType
from app.models.session_state_summary import (
    ExecutionState,
    KeyDecision,
    KnowledgeState,
    SessionStateSummary,
    UserContext,
)

logger = logging.getLogger(__name__)


class SessionStateSummaryManager:
    """Manages session state summaries for cross-session continuity."""

    # FR-SS-001: Extraction triggers
    TRIGGER_CONTEXT_THRESHOLD = 0.80   # Context usage >= 80%
    TRIGGER_SESSION_END = "session_end"
    TRIGGER_USER_REQUEST = "user_request"

    # Redis key pattern for summary cache
    REDIS_KEY_PATTERN = "shardflow:{user_id}:sss:{task_id}:latest"

    def __init__(self) -> None:
        pass

    # ------------------------------------------------------------------
    # FR-SS-001: Automatic summary extraction
    # ------------------------------------------------------------------

    async def extract_summary(
        self,
        user_id: str,
        task_id: str,
        session_seq: int = 1,
        task_type: str = "",
        task_goal: str = "",
        messages: list[dict[str, Any]] | None = None,
        context_summary: str = "",
        intent_stack: list[str] | None = None,
        trigger: str = "session_end",
    ) -> SessionStateSummary:
        """Extract a session state summary from the current session context.

        Trigger conditions (FR-SS-001):
        - Context usage exceeds threshold (80%)
        - Session end (user close or timeout)
        - User explicit request to seal

        Args:
            user_id: User identifier
            task_id: Task identifier
            session_seq: Session sequence number
            task_type: Type of task (research, code_analysis, etc.)
            task_goal: Goal of the task
            messages: List of message dicts from the session
            context_summary: Existing context summary (from compression)
            intent_stack: Current intent stack
            trigger: What triggered this extraction
        """
        # Build knowledge state from available context
        knowledge_state = self._build_knowledge_state(
            messages=messages or [],
            context_summary=context_summary,
        )

        # Build user context
        user_context = self._build_user_context(messages=messages or [])

        # Build execution state
        execution_state = self._build_execution_state(
            messages=messages or [],
            intent_stack=intent_stack or [],
        )

        # Build source preference
        source_preference = self._build_source_preference(messages=messages or [])

        summary = SessionStateSummary(
            summary_id=f"ss_{uuid.uuid4().hex[:12]}",
            user_id=user_id,
            task_id=task_id,
            session_seq=session_seq,
            task_type=task_type,
            task_goal=task_goal or (intent_stack[0] if intent_stack else ""),
            knowledge_state=knowledge_state,
            user_context=user_context,
            execution_state=execution_state,
            source_preference=source_preference,
            version=1,
        )

        logger.info(
            "Session state summary extracted: summary_id=%s, task_id=%s, trigger=%s",
            summary.summary_id, task_id, trigger,
        )

        return summary

    async def extract_and_save(
        self,
        user_id: str,
        task_id: str,
        session_seq: int = 1,
        task_type: str = "",
        task_goal: str = "",
        messages: list[dict[str, Any]] | None = None,
        context_summary: str = "",
        intent_stack: list[str] | None = None,
        trigger: str = "session_end",
    ) -> SessionStateSummary:
        """Extract a summary and persist it to L1 (Redis) + L2 (PostgreSQL)."""
        summary = await self.extract_summary(
            user_id=user_id,
            task_id=task_id,
            session_seq=session_seq,
            task_type=task_type,
            task_goal=task_goal,
            messages=messages,
            context_summary=context_summary,
            intent_stack=intent_stack,
            trigger=trigger,
        )

        # Save via MemoryOrchestrator (L0 + L1 + L2)
        await memory_orchestrator.write_summary(
            user_id, task_id, summary.model_dump(mode="json")
        )

        # Also save to Redis with structured key for fast lookup
        await self._save_to_redis_cache(summary)

        return summary

    def _build_knowledge_state(
        self,
        messages: list[dict[str, Any]],
        context_summary: str = "",
    ) -> KnowledgeState:
        """Build KnowledgeState from messages and existing context summary."""
        confirmed: list[str] = []
        excluded: list[str] = []
        pending: list[str] = []
        key_decisions: list[KeyDecision] = []

        # Parse existing context summary for structured knowledge
        if context_summary:
            self._parse_summary_lines(context_summary, confirmed, excluded, pending)

        # Scan messages for decision patterns
        for msg in messages:
            content = msg.get("content", "")
            role = msg.get("role", "")

            # Look for confirmation patterns
            if role == "assistant":
                if any(kw in content for kw in ["确认", "已确认", "结论是", "确定使用"]):
                    # Extract the confirmed statement (simplified)
                    line = content[:200].strip()
                    if line and line not in confirmed:
                        confirmed.append(line)

                if any(kw in content for kw in ["排除", "不考虑", "放弃"]):
                    line = content[:200].strip()
                    if line and line not in excluded:
                        excluded.append(line)

            # Look for pending items
            if role == "assistant":
                if any(kw in content for kw in ["待办", "接下来", "还需要", "下一步"]):
                    line = content[:200].strip()
                    if line and line not in pending:
                        pending.append(line)

        return KnowledgeState(
            confirmed=confirmed,
            excluded=excluded,
            pending=pending,
            key_decisions=key_decisions,
        )

    def _parse_summary_lines(
        self, summary: str,
        confirmed: list[str], excluded: list[str], pending: list[str],
    ) -> None:
        """Parse a text summary into structured knowledge categories."""
        for line in summary.split("\n"):
            line = line.strip().lstrip("- ").strip()
            if not line:
                continue
            if line.startswith("已确认") or line.startswith("确认结论"):
                content = line.split("：", 1)[-1].strip() if "：" in line else line.split(":", 1)[-1].strip()
                if content:
                    confirmed.append(content)
            elif line.startswith("已排除") or line.startswith("排除方案"):
                content = line.split("：", 1)[-1].strip() if "：" in line else line.split(":", 1)[-1].strip()
                if content:
                    excluded.append(content)
            elif line.startswith("待办") or line.startswith("待深入"):
                content = line.split("：", 1)[-1].strip() if "：" in line else line.split(":", 1)[-1].strip()
                if content:
                    pending.append(content)

    def _build_user_context(
        self, messages: list[dict[str, Any]],
    ) -> UserContext:
        """Build UserContext from messages (heuristic)."""
        # Default values; will be enhanced by UserProfile in P3
        expertise_level = "intermediate"
        preferred_depth = "architecture_level"
        communication_style = "concise"

        # Simple heuristic: count technical terms
        total_content = " ".join(m.get("content", "") for m in messages)
        tech_terms = sum(1 for kw in ["架构", "API", "数据库", "微服务", "向量", "模型"]
                        if kw in total_content)
        if tech_terms >= 3:
            expertise_level = "advanced"
        elif tech_terms <= 1:
            expertise_level = "beginner"

        return UserContext(
            expertise_level=expertise_level,
            preferred_depth=preferred_depth,
            communication_style=communication_style,
        )

    def _build_execution_state(
        self,
        messages: list[dict[str, Any]],
        intent_stack: list[str],
    ) -> ExecutionState:
        """Build ExecutionState from messages and intent stack."""
        tools_used: list[str] = []
        for msg in messages:
            metadata = msg.get("metadata", {})
            tool_name = metadata.get("tool_name", "")
            if tool_name and tool_name not in tools_used:
                tools_used.append(tool_name)

        return ExecutionState(
            completed_steps=len(messages),
            current_step=intent_stack[-1] if intent_stack else "",
            tools_used=tools_used,
            estimated_remaining="",
        )

    def _build_source_preference(
        self, messages: list[dict[str, Any]],
    ) -> dict[str, float]:
        """Build source preference from messages."""
        # Default source preferences
        return {
            "official_doc": 0.8,
            "web_search": 0.6,
            "stackoverflow": 0.3,
        }

    # ------------------------------------------------------------------
    # FR-SS-002: Summary injection into new sessions
    # ------------------------------------------------------------------

    async def inject_summary(
        self, user_id: str, task_id: str,
    ) -> str | None:
        """Load the latest summary for a task and format it for LLM Prompt injection.

        Per FR-SS-002: System auto-prepend to LLM Prompt when a related
        unfinished task is detected at new session startup.

        Returns:
            Formatted injection text, or None if no summary found.
        """
        summary = await self.load_latest_summary(user_id, task_id)
        if summary is None:
            return None

        return self.format_injection_text(summary)

    def format_injection_text(self, summary: SessionStateSummary) -> str:
        """Format a summary into the injection protocol text per FR-SS-002.

        Injection protocol:
        [系统注入] 基于之前探索状态（会话 N/M）：
        - 已确认：...
        - 已排除：...
        - 待深入：...
        - 来源偏好：...
        - 执行进度：...

        请继续，无需重复确认上述结论。
        """
        ks = summary.knowledge_state
        es = summary.execution_state

        parts = [
            f"[系统注入] 基于之前探索状态（会话 {summary.session_seq}）：",
        ]

        if ks.confirmed:
            parts.append("- 已确认：" + "；".join(ks.confirmed))
        if ks.excluded:
            parts.append("- 已排除：" + "；".join(ks.excluded))
        if ks.pending:
            parts.append("- 待深入：" + "；".join(ks.pending))
        if summary.source_preference:
            pref_str = "、".join(
                f"{k}(权重{v:.1f})" for k, v in summary.source_preference.items()
            )
            parts.append(f"- 来源偏好：{pref_str}")
        if es.current_step:
            parts.append(f"- 执行进度：已完成{es.completed_steps}步，当前：{es.current_step}")

        parts.append("\n请继续，无需重复确认上述结论。")

        return "\n".join(parts)

    # ------------------------------------------------------------------
    # FR-SS-003: Cross-port session continuation
    # ------------------------------------------------------------------

    async def find_unfinished_tasks(self, user_id: str) -> list[dict[str, Any]]:
        """Find unfinished tasks for a user across all ports.

        Scans Redis for recent session state summaries that indicate
        incomplete tasks.
        """
        try:
            from app.infrastructure.redis_client import redis_client
            r = await redis_client.get_redis()

            unfinished: list[dict[str, Any]] = []
            pattern = f"shardflow:{user_id}:sss:*:latest"

            async for key in r.scan_iter(match=pattern, count=50):
                raw = await r.get(key)
                if raw:
                    try:
                        data = json.loads(raw)
                        # Check if task appears unfinished
                        exec_state = data.get("execution_state", {})
                        remaining = exec_state.get("estimated_remaining", "")
                        if remaining and remaining != "0%" and remaining != "100%":
                            unfinished.append(data)
                    except (json.JSONDecodeError, TypeError):
                        continue

            return unfinished

        except Exception as e:
            logger.warning("Failed to find unfinished tasks for user %s: %s", user_id, e)
            return []

    async def resume_task(
        self, user_id: str, task_id: str, source_port: str = "Web",
    ) -> dict[str, Any] | None:
        """Resume a task from its latest session state summary.

        Per FR-SS-003: Auto-identify user + associate recent unfinished
        task -> restore from summary.

        Args:
            user_id: User identifier
            task_id: Task to resume
            source_port: The port the user is connecting from (Web/Feishu/DingTalk/CLI)

        Returns:
            Resumed state dict with injection text, or None.
        """
        summary = await self.load_latest_summary(user_id, task_id)
        if summary is None:
            return None

        injection_text = self.format_injection_text(summary)

        return {
            "resumed": True,
            "task_id": task_id,
            "source_port": source_port,
            "summary": summary.model_dump(mode="json"),
            "injection_text": injection_text,
            "session_seq": summary.session_seq,
        }

    # ------------------------------------------------------------------
    # FR-SS-004: Summary version management
    # ------------------------------------------------------------------

    async def save_new_version(
        self, summary: SessionStateSummary,
    ) -> SessionStateSummary:
        """Save a new version of a session state summary.

        Per FR-SS-004: Each update creates a new version, preserving history.
        """
        # Load current version to determine next version number
        existing = await self.load_latest_summary(summary.user_id, summary.task_id)
        if existing:
            summary.version = existing.version + 1
            summary.session_seq = existing.session_seq
        else:
            summary.version = 1

        # Generate new summary_id for the new version
        summary.summary_id = f"ss_{uuid.uuid4().hex[:12]}"
        summary.updated_at = datetime.now(timezone.utc)

        # Persist
        await memory_orchestrator.write_summary(
            summary.user_id, summary.task_id, summary.model_dump(mode="json")
        )
        await self._save_to_redis_cache(summary)

        logger.info(
            "Summary version saved: summary_id=%s, task_id=%s, version=%d",
            summary.summary_id, summary.task_id, summary.version,
        )

        return summary

    async def get_version_history(
        self, user_id: str, task_id: str,
    ) -> list[dict[str, Any]]:
        """Get version history for a task's summaries.

        Returns a list of summary versions, newest first.
        """
        try:
            results = await memory_orchestrator.search(
                user_id,
                MemoryType.SESSION_SUMMARY,
                query=type("Q", (), {"key_prefix": task_id, "limit": 50})(),
            )
            versions = []
            for record in results:
                data = record.data
                versions.append({
                    "summary_id": data.get("summary_id", ""),
                    "version": data.get("version", 1),
                    "updated_at": data.get("updated_at", ""),
                    "session_seq": data.get("session_seq", 1),
                })
            # Sort by version descending
            versions.sort(key=lambda v: v["version"], reverse=True)
            return versions
        except Exception as e:
            logger.warning("Failed to get version history: %s", e)
            return []

    async def compare_versions(
        self, user_id: str, task_id: str,
        version_a: int, version_b: int,
    ) -> dict[str, Any] | None:
        """Compare two versions of a summary.

        Returns a diff-like structure showing changes between versions.
        """
        try:
            results = await memory_orchestrator.search(
                user_id,
                MemoryType.SESSION_SUMMARY,
                query=type("Q", (), {"key_prefix": task_id, "limit": 50})(),
            )

            version_map: dict[int, dict[str, Any]] = {}
            for record in results:
                data = record.data
                v = data.get("version", 1)
                version_map[v] = data

            summary_a = version_map.get(version_a)
            summary_b = version_map.get(version_b)

            if not summary_a or not summary_b:
                return None

            # Compare knowledge states
            ks_a = summary_a.get("knowledge_state", {})
            ks_b = summary_b.get("knowledge_state", {})

            return {
                "version_a": version_a,
                "version_b": version_b,
                "confirmed_added": list(set(ks_b.get("confirmed", [])) - set(ks_a.get("confirmed", []))),
                "confirmed_removed": list(set(ks_a.get("confirmed", [])) - set(ks_b.get("confirmed", []))),
                "excluded_added": list(set(ks_b.get("excluded", [])) - set(ks_a.get("excluded", []))),
                "excluded_removed": list(set(ks_a.get("excluded", [])) - set(ks_b.get("excluded", []))),
                "pending_added": list(set(ks_b.get("pending", [])) - set(ks_a.get("pending", []))),
                "pending_removed": list(set(ks_a.get("pending", [])) - set(ks_b.get("pending", []))),
            }
        except Exception as e:
            logger.warning("Failed to compare versions: %s", e)
            return None

    async def rollback_to_version(
        self, user_id: str, task_id: str, target_version: int,
    ) -> SessionStateSummary | None:
        """Rollback a summary to a specific version.

        Creates a new version that is a copy of the target version.
        """
        try:
            results = await memory_orchestrator.search(
                user_id,
                MemoryType.SESSION_SUMMARY,
                query=type("Q", (), {"key_prefix": task_id, "limit": 50})(),
            )

            for record in results:
                data = record.data
                if data.get("version") == target_version:
                    # Create a new version as a copy
                    rollback_summary = SessionStateSummary(**data)
                    return await self.save_new_version(rollback_summary)

        except Exception as e:
            logger.warning("Failed to rollback to version %d: %s", target_version, e)

        return None

    # ------------------------------------------------------------------
    # Load helpers
    # ------------------------------------------------------------------

    async def load_latest_summary(
        self, user_id: str, task_id: str,
    ) -> SessionStateSummary | None:
        """Load the latest session state summary for a task.

        Tries Redis cache first, then falls back to MemoryOrchestrator.
        """
        # Try Redis cache first
        try:
            from app.infrastructure.redis_client import redis_client
            r = await redis_client.get_redis()
            cache_key = self.REDIS_KEY_PATTERN.format(user_id=user_id, task_id=task_id)
            raw = await r.get(cache_key)
            if raw:
                data = json.loads(raw)
                return SessionStateSummary(**data)
        except Exception as e:
            logger.debug("Redis cache miss for summary %s/%s: %s", user_id, task_id, e)

        # Fall back to MemoryOrchestrator
        try:
            data = await memory_orchestrator.read_summary(user_id, task_id)
            if data:
                return SessionStateSummary(**data)
        except Exception as e:
            logger.warning("Failed to load summary from orchestrator: %s", e)

        return None

    async def _save_to_redis_cache(self, summary: SessionStateSummary) -> None:
        """Save summary to Redis with structured key for fast lookup."""
        try:
            from app.infrastructure.redis_client import redis_client
            r = await redis_client.get_redis()
            cache_key = self.REDIS_KEY_PATTERN.format(
                user_id=summary.user_id, task_id=summary.task_id,
            )
            await r.set(cache_key, summary.model_dump_json(), ex=86400)  # 24h TTL
        except Exception as e:
            logger.warning("Failed to save summary to Redis cache: %s", e)


# Global singleton
session_state_summary_manager = SessionStateSummaryManager()
