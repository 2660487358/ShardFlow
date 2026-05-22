"""MemoryOrchestrator — unified entry point for all memory operations.

Routes read/write/delete/search by MemoryType to the appropriate CompositeAdapter.
Upper-layer code (LangGraph nodes, PromptEngine, ContextManager) calls ONLY this,
never individual adapters directly.

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
        record = await orchestrator.read(user_id, MemoryType.LONG_TERM, task_id)
        await orchestrator.write(user_id, MemoryType.LONG_TERM, task_id, data)
    """

    def __init__(self) -> None:
        # SHORT_TERM: session-scoped messages — use L0+Redis (no Java for ephemeral data)
        self._short_term = CompositeAdapter()
        # LONG_TERM: ContextShard packages — full L0→L1→L2 chain
        self._long_term = CompositeAdapter()
        # META: Strategy records — Redis + Java (L0 less useful for search-heavy meta)
        self._meta = CompositeAdapter()

    def _adapter_for(self, memory_type: MemoryType) -> CompositeAdapter:
        mapping: dict[MemoryType, CompositeAdapter] = {
            MemoryType.SHORT_TERM: self._short_term,
            MemoryType.LONG_TERM: self._long_term,
            MemoryType.META: self._meta,
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
    # Convenience: shard-specific operations
    # ------------------------------------------------------------------

    async def read_shard(self, user_id: str, task_id: str) -> dict[str, Any] | None:
        """Read a LONG_TERM shard and return raw data dict (convenience)."""
        record = await self.read(user_id, MemoryType.LONG_TERM, task_id)
        return record.data if record else None

    async def write_shard(self, user_id: str, task_id: str,
                          shard_data: dict[str, Any]) -> MemoryRecord:
        """Write a LONG_TERM shard (convenience)."""
        return await self.write(user_id, MemoryType.LONG_TERM, task_id, shard_data)

    async def read_strategy(self, user_id: str, strategy_id: str) -> dict[str, Any] | None:
        """Read a META strategy record (convenience)."""
        record = await self.read(user_id, MemoryType.META, strategy_id)
        return record.data if record else None

    async def write_strategy(self, user_id: str, strategy_id: str,
                             strategy_data: dict[str, Any]) -> MemoryRecord:
        """Write a META strategy record (convenience)."""
        return await self.write(user_id, MemoryType.META, strategy_id, strategy_data)

    async def read_session(self, user_id: str, session_id: str) -> dict[str, Any] | None:
        """Read a SHORT_TERM session context (convenience)."""
        record = await self.read(user_id, MemoryType.SHORT_TERM, session_id)
        return record.data if record else None

    async def write_session(self, user_id: str, session_id: str,
                            session_data: dict[str, Any]) -> MemoryRecord:
        """Write a SHORT_TERM session context (convenience)."""
        return await self.write(user_id, MemoryType.SHORT_TERM, session_id, session_data)


# Global singleton
memory_orchestrator = MemoryOrchestrator()
