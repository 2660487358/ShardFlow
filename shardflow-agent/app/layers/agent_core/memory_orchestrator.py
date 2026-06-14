"""MemoryOrchestrator — unified entry point for all memory operations.

Routes read/write/delete/search by MemoryType to the appropriate CompositeAdapter.
Upper-layer code (LangGraph nodes, PromptEngine, ContextManager) calls ONLY this,
never individual adapters directly.

Four-layer memory model:
- SHORT_TERM:      Session-scoped working memory (L0 + L1 only)
- SESSION_SUMMARY: Cross-session state snapshots (L0 + L1 + L2)
- SEMANTIC:        User facts, preferences, profile (L0 + L1 + L2)
- EPISODIC:        Decision paths, historical events (L0 + L1 + L2)
"""
import logging
from typing import Any

from app.models.memory import MemoryQuery, MemoryRecord, MemoryType
from app.layers.agent_core.memory_adapters import CompositeAdapter

logger = logging.getLogger(__name__)


class MemoryOrchestrator:
    """Central memory coordinator. One adapter set per memory type.

    Usage:
        orchestrator = MemoryOrchestrator()
        record = await orchestrator.read(user_id, MemoryType.SESSION_SUMMARY, task_id)
        await orchestrator.write(user_id, MemoryType.SEMANTIC, key, data)
    """

    def __init__(self) -> None:
        # SHORT_TERM: session-scoped messages — use L0+Redis (no Java for ephemeral data)
        self._short_term = CompositeAdapter(use_l2=False)
        # SESSION_SUMMARY: cross-session state snapshots — full L0→L1→L2 chain
        self._session_summary = CompositeAdapter(use_l2=True)
        # SEMANTIC: user facts and preferences — full L0→L1→L2 chain
        self._semantic = CompositeAdapter(use_l2=True)
        # EPISODIC: decision paths and events — full L0→L1→L2 chain
        self._episodic = CompositeAdapter(use_l2=True)

    def _adapter_for(self, memory_type: MemoryType) -> CompositeAdapter:
        mapping: dict[MemoryType, CompositeAdapter] = {
            MemoryType.SHORT_TERM: self._short_term,
            MemoryType.SESSION_SUMMARY: self._session_summary,
            MemoryType.SEMANTIC: self._semantic,
            MemoryType.EPISODIC: self._episodic,
        }
        return mapping[memory_type]

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------

    async def read(self, user_id: str, memory_type: MemoryType, key: str) -> MemoryRecord | None:
        """Read memory through L0→L1→L2 degrade chain."""
        adapter = self._adapter_for(memory_type)
        return await adapter.read(user_id, memory_type, key)

    # ------------------------------------------------------------------
    # Write
    # ------------------------------------------------------------------

    async def write(self, user_id: str, memory_type: MemoryType, key: str,
                    data: dict[str, Any], ttl_seconds: int = 0) -> MemoryRecord:
        """Write memory: broadcast to all tiers (L2 authoritative)."""
        adapter = self._adapter_for(memory_type)
        return await adapter.write(user_id, memory_type, key, data, ttl_seconds)

    # ------------------------------------------------------------------
    # Delete
    # ------------------------------------------------------------------

    async def delete(self, user_id: str, memory_type: MemoryType, key: str) -> bool:
        adapter = self._adapter_for(memory_type)
        return await adapter.delete(user_id, memory_type, key)

    # ------------------------------------------------------------------
    # Search
    # ------------------------------------------------------------------

    async def search(self, user_id: str, memory_type: MemoryType,
                     query: MemoryQuery) -> list[MemoryRecord]:
        adapter = self._adapter_for(memory_type)
        return await adapter.search(user_id, memory_type, query)

    # ------------------------------------------------------------------
    # Exists
    # ------------------------------------------------------------------

    async def exists(self, user_id: str, memory_type: MemoryType, key: str) -> bool:
        adapter = self._adapter_for(memory_type)
        return await adapter.exists(user_id, memory_type, key)

    # ------------------------------------------------------------------
    # Convenience: type-specific operations
    # ------------------------------------------------------------------

    async def read_session(self, user_id: str, session_id: str) -> dict[str, Any] | None:
        """Read a SHORT_TERM session context (convenience)."""
        record = await self.read(user_id, MemoryType.SHORT_TERM, session_id)
        return record.data if record else None

    async def write_session(self, user_id: str, session_id: str,
                            session_data: dict[str, Any]) -> MemoryRecord:
        """Write a SHORT_TERM session context (convenience)."""
        return await self.write(user_id, MemoryType.SHORT_TERM, session_id, session_data)

    async def delete_session(self, user_id: str, session_id: str) -> bool:
        """Delete a SHORT_TERM session context (convenience)."""
        return await self.delete(user_id, MemoryType.SHORT_TERM, session_id)

    async def read_summary(self, user_id: str, task_id: str) -> dict[str, Any] | None:
        """Read a SESSION_SUMMARY state snapshot (convenience)."""
        record = await self.read(user_id, MemoryType.SESSION_SUMMARY, task_id)
        return record.data if record else None

    async def write_summary(self, user_id: str, task_id: str,
                            summary_data: dict[str, Any]) -> MemoryRecord:
        """Write a SESSION_SUMMARY state snapshot (convenience)."""
        return await self.write(user_id, MemoryType.SESSION_SUMMARY, task_id, summary_data)

    async def delete_summary(self, user_id: str, task_id: str) -> bool:
        """Delete a SESSION_SUMMARY state snapshot (convenience)."""
        return await self.delete(user_id, MemoryType.SESSION_SUMMARY, task_id)

    async def read_semantic(self, user_id: str, key: str) -> dict[str, Any] | None:
        """Read a SEMANTIC memory chunk (convenience)."""
        record = await self.read(user_id, MemoryType.SEMANTIC, key)
        return record.data if record else None

    async def write_semantic(self, user_id: str, key: str,
                             data: dict[str, Any]) -> MemoryRecord:
        """Write a SEMANTIC memory chunk (convenience)."""
        return await self.write(user_id, MemoryType.SEMANTIC, key, data)

    async def delete_semantic(self, user_id: str, key: str) -> bool:
        """Delete a SEMANTIC memory chunk (convenience)."""
        return await self.delete(user_id, MemoryType.SEMANTIC, key)

    async def read_episodic(self, user_id: str, key: str) -> dict[str, Any] | None:
        """Read an EPISODIC memory chunk (convenience)."""
        record = await self.read(user_id, MemoryType.EPISODIC, key)
        return record.data if record else None

    async def write_episodic(self, user_id: str, key: str,
                             data: dict[str, Any]) -> MemoryRecord:
        """Write an EPISODIC memory chunk (convenience)."""
        return await self.write(user_id, MemoryType.EPISODIC, key, data)

    async def delete_episodic(self, user_id: str, key: str) -> bool:
        """Delete an EPISODIC memory chunk (convenience)."""
        return await self.delete(user_id, MemoryType.EPISODIC, key)

    # ------------------------------------------------------------------
    # Backward compatibility aliases (deprecated — use new methods)
    # ------------------------------------------------------------------

    async def read_shard(self, user_id: str, task_id: str) -> dict[str, Any] | None:
        """Read a SESSION_SUMMARY (backward compat alias for read_summary)."""
        return await self.read_summary(user_id, task_id)

    async def write_shard(self, user_id: str, task_id: str,
                          shard_data: dict[str, Any]) -> MemoryRecord:
        """Write a SESSION_SUMMARY (backward compat alias for write_summary)."""
        return await self.write_summary(user_id, task_id, shard_data)


# Global singleton
memory_orchestrator = MemoryOrchestrator()
