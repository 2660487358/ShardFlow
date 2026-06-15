"""ContextAssembler — 上下文组装器 (FR-RR-005).

Assembles memory context for LLM Prompt injection with token budget management.

Per spec section 4.4 FR-RR-005:
- Priority-based injection into LLM Prompt:
  1. System-level memory (high priority, 30% token budget)
  2. User profile (medium priority, 30% token budget)
  3. Historical episodic (low priority, by time desc, 30% token budget)
  4. 10% token budget reserved as buffer

Token budget is derived from settings.memory_assemble_token_budget (default 4096),
decoupled from model context limit.
"""
import logging
import time as _time
from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, Field

from app.layers.agent_core.context_manager import context_manager
from app.layers.agent_core.memory_search_engine import (
    MemorySearchEngine,
    SearchFilters,
    SearchRequest,
    memory_search_engine,
)
from app.layers.agent_core.user_profile_manager import user_profile_manager
from app.models.memory import MemoryType

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Context section models
# ---------------------------------------------------------------------------

class ContextSection(BaseModel):
    """A section of assembled context with priority and token budget."""
    section_type: str          # system | profile | episodic | buffer
    priority: int              # 1 (highest) to 4 (lowest)
    content: str = ""
    token_count: int = 0
    budget_ratio: float = 0.0  # Fraction of total budget allocated

    model_config = {"extra": "allow"}


class AssembledContext(BaseModel):
    """Complete assembled context ready for LLM Prompt injection."""
    sections: list[ContextSection] = Field(default_factory=list)
    total_tokens: int = 0
    total_budget: int = 0
    overflow: bool = False     # True if content exceeded budget
    user_id: str = ""

    model_config = {"extra": "allow"}

    def to_prompt_text(self) -> str:
        """Render the assembled context as a single prompt text string."""
        parts: list[str] = []
        for section in self.sections:
            if section.content:
                parts.append(section.content)
        return "\n\n".join(parts)


# ---------------------------------------------------------------------------
# Token budget allocation (per FR-RR-005)
# ---------------------------------------------------------------------------

class TokenBudget:
    """Token budget allocation ratios per spec FR-RR-005.

    All ratios are read from settings.MEMORY_ASSEMBLE_* configuration.
    """

    @classmethod
    @property
    def SYSTEM_RATIO(cls) -> float:
        from app.config import settings
        return settings.memory_assemble_system_ratio

    @classmethod
    @property
    def PROFILE_RATIO(cls) -> float:
        from app.config import settings
        return settings.memory_assemble_profile_ratio

    @classmethod
    @property
    def EPISODIC_RATIO(cls) -> float:
        from app.config import settings
        return settings.memory_assemble_episodic_ratio

    @classmethod
    @property
    def BUFFER_RATIO(cls) -> float:
        from app.config import settings
        return settings.memory_assemble_buffer_ratio

    @classmethod
    def allocate(cls, total_budget: int) -> dict[str, int]:
        """Allocate token budget across sections.

        Returns dict mapping section_type -> token count.
        """
        return {
            "system": int(total_budget * cls.SYSTEM_RATIO),
            "profile": int(total_budget * cls.PROFILE_RATIO),
            "episodic": int(total_budget * cls.EPISODIC_RATIO),
            "buffer": int(total_budget * cls.BUFFER_RATIO),
        }


# ---------------------------------------------------------------------------
# ContextAssembler
# ---------------------------------------------------------------------------

class ContextAssembler:
    """Assembles memory context for LLM Prompt injection with token budget.

    Usage:
        assembler = ContextAssembler()
        context = await assembler.assemble(user_id="user_001", query="RAG方案调研")
        prompt_text = context.to_prompt_text()
    """

    def __init__(self, search_engine: MemorySearchEngine | None = None) -> None:
        self._engine = search_engine or memory_search_engine

    # ------------------------------------------------------------------
    # Main assembly entry point
    # ------------------------------------------------------------------

    async def assemble(
        self,
        user_id: str,
        query: str = "",
        query_vector: list[float] | None = None,
        session_id: str = "",
        task_id: str = "",
        extra_system_context: str = "",
        token_budget: int | None = None,
    ) -> AssembledContext:
        """Assemble memory context for LLM Prompt injection.

        Per FR-RR-005, assembles context in priority order:
        1. System-level memory (30% budget)
        2. User profile (30% budget)
        3. Historical episodic (30% budget)
        4. Buffer (10% reserved)

        token_budget: Memory injection token budget, decoupled from model context limit.
                      Defaults to settings.memory_assemble_token_budget (4096).
        """
        from app.config import settings

        # Calculate total token budget (decoupled from model context limit)
        if token_budget is None:
            token_budget = settings.memory_assemble_token_budget
        total_budget = token_budget
        budgets = TokenBudget.allocate(total_budget)

        # 4B-02: Track assembly duration
        start_time = _time.monotonic()

        sections: list[ContextSection] = []
        total_tokens = 0

        # Section 1: System-level memory (high priority)
        system_section = await self._assemble_system(
            user_id=user_id,
            budget=budgets["system"],
            session_id=session_id,
            task_id=task_id,
            extra_context=extra_system_context,
        )
        sections.append(system_section)
        total_tokens += system_section.token_count

        # Section 2: User profile (medium priority)
        profile_section = await self._assemble_profile(
            user_id=user_id,
            budget=budgets["profile"],
        )
        sections.append(profile_section)
        total_tokens += profile_section.token_count

        # Section 3: Historical episodic (low priority)
        episodic_section = await self._assemble_episodic(
            user_id=user_id,
            query=query,
            query_vector=query_vector,
            budget=budgets["episodic"],
        )
        sections.append(episodic_section)
        total_tokens += episodic_section.token_count

        # Section 4: Buffer (reserved, empty by design)
        buffer_section = ContextSection(
            section_type="buffer",
            priority=4,
            content="",
            token_count=0,
            budget_ratio=TokenBudget.BUFFER_RATIO,
        )
        sections.append(buffer_section)

        # Check for overflow
        overflow = total_tokens > total_budget

        assembled = AssembledContext(
            sections=sections,
            total_tokens=total_tokens,
            total_budget=total_budget,
            overflow=overflow,
            user_id=user_id,
        )

        logger.info(
            "Assembled context for user %s: %d tokens / %d budget, overflow=%s",
            user_id, total_tokens, total_budget, overflow,
        )

        # 4B-02: Record assembly metrics
        try:
            from app.infrastructure.memory_metrics import memory_metrics
            elapsed_ms = (_time.monotonic() - start_time) * 1000
            section_tokens = {s.section_type: s.token_count for s in sections}
            memory_metrics.record_assembly(
                elapsed_ms=elapsed_ms,
                section_tokens=section_tokens,
                total_tokens=total_tokens,
                total_budget=total_budget,
                overflow=overflow,
            )
        except Exception:
            pass  # Metrics recording is non-critical

        return assembled

    # ------------------------------------------------------------------
    # Section 1: System-level memory
    # ------------------------------------------------------------------

    async def _assemble_system(
        self,
        user_id: str,
        budget: int,
        session_id: str = "",
        task_id: str = "",
        extra_context: str = "",
    ) -> ContextSection:
        """Assemble system-level memory context.

        Includes:
        - Session state summary (if resuming a task)
        - Task context
        - Extra system context (e.g., tool results, system messages)
        """
        parts: list[str] = []

        # Load session state summary if task_id is provided
        if task_id:
            from app.layers.agent_core.session_state_summary_manager import (
                session_state_summary_manager,
            )
            summary = await session_state_summary_manager.load_summary(
                user_id=user_id,
                task_id=task_id,
            )
            if summary:
                summary_text = self._format_session_summary(summary)
                parts.append(summary_text)

        # Add extra system context
        if extra_context:
            parts.append(extra_context)

        content = "\n\n".join(parts)
        token_count = self._estimate_tokens(content)

        # Truncate if exceeds budget
        if token_count > budget and budget > 0:
            content = self._truncate_to_budget(content, budget)
            token_count = budget

        return ContextSection(
            section_type="system",
            priority=1,
            content=content,
            token_count=token_count,
            budget_ratio=TokenBudget.SYSTEM_RATIO,
        )

    # ------------------------------------------------------------------
    # Section 2: User profile
    # ------------------------------------------------------------------

    async def _assemble_profile(
        self,
        user_id: str,
        budget: int,
    ) -> ContextSection:
        """Assemble user profile context.

        Uses UserProfileManager.inject_profile() for formatted output.
        """
        try:
            profile_text = await user_profile_manager.inject_profile(user_id)
        except Exception as e:
            logger.warning("Failed to inject profile for user %s: %s", user_id, e)
            profile_text = ""

        token_count = self._estimate_tokens(profile_text)

        # Truncate if exceeds budget
        if token_count > budget and budget > 0:
            profile_text = self._truncate_to_budget(profile_text, budget)
            token_count = budget

        return ContextSection(
            section_type="profile",
            priority=2,
            content=profile_text,
            token_count=token_count,
            budget_ratio=TokenBudget.PROFILE_RATIO,
        )

    # ------------------------------------------------------------------
    # Section 3: Historical episodic
    # ------------------------------------------------------------------

    async def _assemble_episodic(
        self,
        user_id: str,
        query: str,
        query_vector: list[float] | None,
        budget: int,
    ) -> ContextSection:
        """Assemble historical episodic memory context.

        Searches for relevant episodic memories and formats them
        in reverse chronological order within the token budget.
        """
        if not query and not query_vector:
            return ContextSection(
                section_type="episodic",
                priority=3,
                content="",
                token_count=0,
                budget_ratio=TokenBudget.EPISODIC_RATIO,
            )

        # Search for relevant episodic memories
        search_filters = SearchFilters(
            memory_types=[MemoryType.EPISODIC],
            min_confidence=0.5,
        )

        try:
            from app.config import settings
            search_top_k = settings.memory_search_top_k
            search_min_similarity = settings.memory_search_min_similarity

            if query_vector:
                results = await self._engine.hybrid_search(
                    user_id=user_id,
                    query=query,
                    query_vector=query_vector,
                    filters=search_filters,
                    top_k=search_top_k,
                    similarity_threshold=search_min_similarity,
                )
            else:
                results = await self._engine.structured_search(
                    user_id=user_id,
                    filters=search_filters,
                    limit=search_top_k,
                )
        except Exception as e:
            logger.warning("Episodic memory search failed for user %s: %s", user_id, e)
            results = []

        if not results:
            return ContextSection(
                section_type="episodic",
                priority=3,
                content="",
                token_count=0,
                budget_ratio=TokenBudget.EPISODIC_RATIO,
            )

        # Format results in reverse chronological order
        content = self._format_episodic_results(results)
        token_count = self._estimate_tokens(content)

        # Truncate if exceeds budget
        if token_count > budget and budget > 0:
            content = self._truncate_to_budget(content, budget)
            token_count = budget

        return ContextSection(
            section_type="episodic",
            priority=3,
            content=content,
            token_count=token_count,
            budget_ratio=TokenBudget.EPISODIC_RATIO,
        )

    # ------------------------------------------------------------------
    # Formatting helpers
    # ------------------------------------------------------------------

    def _format_session_summary(self, summary: dict[str, Any]) -> str:
        """Format a session state summary for prompt injection.

        Per spec FR-SS-002 injection protocol:
        [系统注入] 基于之前探索状态（会话 N/M）：
        - 已确认：...
        - 已排除：...
        - 待深入：...
        - 来源偏好：...
        - 执行进度：...
        请继续，无需重复确认上述结论。
        """
        knowledge_state = summary.get("knowledge_state", {})
        confirmed = knowledge_state.get("confirmed", [])
        excluded = knowledge_state.get("excluded", [])
        pending = knowledge_state.get("pending", [])
        key_decisions = knowledge_state.get("key_decisions", [])

        execution_state = summary.get("execution_state", {})
        source_pref = summary.get("source_preference", {})

        lines = ["[系统注入] 基于之前探索状态："]

        if confirmed:
            lines.append("- 已确认：" + "；".join(confirmed[:10]))
        if excluded:
            lines.append("- 已排除：" + "；".join(excluded[:10]))
        if pending:
            lines.append("- 待深入：" + "；".join(pending[:10]))
        if key_decisions:
            decision_texts = []
            for d in key_decisions[:5]:
                if isinstance(d, dict):
                    decision_texts.append(d.get("decision", ""))
                elif isinstance(d, str):
                    decision_texts.append(d)
            if decision_texts:
                lines.append("- 关键决策：" + "；".join(decision_texts))

        if source_pref:
            pref_strs = [f"{k}({v:.1f})" for k, v in
                         sorted(source_pref.items(), key=lambda x: x[1], reverse=True)[:5]]
            lines.append("- 来源偏好：" + "；".join(pref_strs))

        if execution_state.get("current_step"):
            lines.append(f"- 执行进度：{execution_state.get('current_step', '')}，"
                         f"约{execution_state.get('estimated_remaining', '未知')}待完成")

        lines.append("\n请继续，无需重复确认上述结论。")

        return "\n".join(lines)

    def _format_episodic_results(self, results: list[Any]) -> str:
        """Format episodic search results for prompt injection."""
        if not results:
            return ""

        lines = ["[历史情景记忆]"]

        for i, result in enumerate(results[:10], 1):
            content = result.content_text if hasattr(result, "content_text") else str(result)
            similarity = result.similarity_score if hasattr(result, "similarity_score") else 0.0
            category = result.category if hasattr(result, "category") else ""

            # Truncate individual entries
            content_preview = content[:200] + ("..." if len(content) > 200 else "")
            lines.append(f"{i}. [{category}] {content_preview} (相关度: {similarity:.2f})")

        return "\n".join(lines)

    # ------------------------------------------------------------------
    # Token estimation and truncation
    # ------------------------------------------------------------------

    def _estimate_tokens(self, text: str) -> int:
        """Estimate token count for text (4 chars ≈ 1 token for Chinese)."""
        if not text:
            return 0
        return len(text) // 4

    def _truncate_to_budget(self, text: str, budget: int) -> str:
        """Truncate text to fit within token budget.

        Preserves the beginning of the text (most important context).
        """
        if not text:
            return ""

        # Estimate character limit from token budget
        char_limit = budget * 4  # 4 chars per token

        if len(text) <= char_limit:
            return text

        # Truncate and add ellipsis
        return text[:char_limit - 3] + "..."


# Global singleton
context_assembler = ContextAssembler()
