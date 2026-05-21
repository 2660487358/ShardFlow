"""Memory lifecycle management — creation → storage → retrieval → expiration → cleanup.

Handles TTL-based expiration, active cleanup of expired entries, and session archival.
Uses MemoryOrchestrator for all read/write operations.
"""
import asyncio
import logging
from datetime import datetime, timezone
from typing import Any

from app.models.memory import MemoryQuery, MemoryType

logger = logging.getLogger(__name__)


class MemoryLifecycle:
    """Manages the complete lifecycle of memory records."""

    DEFAULT_TTL_SHORT_TERM = 3600       # 1 hour for session context
    DEFAULT_TTL_LONG_TERM = 86400 * 7   # 7 days for shards
    DEFAULT_TTL_META = 86400 * 30       # 30 days for strategies

    # Cleanup interval: every 30 minutes
    CLEANUP_INTERVAL = 1800

    # Max records per tenant per type
    MAX_SHARDS_PER_TENANT = 1000
    MAX_STRATEGIES_PER_TENANT = 500
    MAX_SESSIONS_PER_TENANT = 200

    def __init__(self) -> None:
        self._cleanup_task: asyncio.Task[Any] | None = None

    def ttl_for(self, memory_type: MemoryType) -> int:
        mapping = {
            MemoryType.SHORT_TERM: self.DEFAULT_TTL_SHORT_TERM,
            MemoryType.LONG_TERM: self.DEFAULT_TTL_LONG_TERM,
            MemoryType.META: self.DEFAULT_TTL_META,
        }
        return mapping[memory_type]

    # ------------------------------------------------------------------
    # Create: configure TTL automatically based on memory type
    # ------------------------------------------------------------------

    async def create_record(self, tenant_id: str, memory_type: MemoryType, key: str,
                            data: dict[str, Any], ttl_seconds: int = 0) -> dict[str, Any]:
        """Create a memory record with auto-TTL if not specified."""
        from app.layers.agent_core.memory_orchestrator import memory_orchestrator

        if ttl_seconds <= 0:
            ttl_seconds = self.ttl_for(memory_type)

        record = await memory_orchestrator.write(tenant_id, memory_type, key, data, ttl_seconds)
        return record.data

    # ------------------------------------------------------------------
    # Archive: move session data to long-term storage on completion
    # ------------------------------------------------------------------

    async def archive_session(self, tenant_id: str, session_id: str) -> bool:
        """Archive a SHORT_TERM session to LONG_TERM shard."""
        from app.layers.agent_core.memory_orchestrator import memory_orchestrator

        session = await memory_orchestrator.read(tenant_id, MemoryType.SHORT_TERM, session_id)
        if session is None:
            return False

        # Move key data to long-term
        task_id = session.data.get("task_id", session_id)
        shard_data = {
            "session_id": session_id,
            "messages": session.data.get("messages", []),
            "summary": session.data.get("summary", ""),
            "archived_at": datetime.now(timezone.utc).isoformat(),
        }
        await memory_orchestrator.write(tenant_id, MemoryType.LONG_TERM, task_id, shard_data)
        await memory_orchestrator.delete(tenant_id, MemoryType.SHORT_TERM, session_id)
        return True

    # ------------------------------------------------------------------
    # Cleanup: remove expired entries across all memory types
    # ------------------------------------------------------------------

    async def cleanup_expired(self, tenant_id: str) -> dict[str, int]:
        """Actively clean up expired memory records for a tenant."""
        from app.layers.agent_core.memory_orchestrator import memory_orchestrator

        cleaned: dict[str, int] = {}
        for memory_type in MemoryType:
            query = MemoryQuery(
                memory_type=memory_type,
                created_before=datetime.now(timezone.utc),
                limit=100,
            )
            records = await memory_orchestrator.search(tenant_id, memory_type, query)
            count = 0
            for record in records:
                if record.ttl_seconds > 0:
                    age = (datetime.now(timezone.utc) - record.updated_at).total_seconds()
                    if age > record.ttl_seconds:
                        await memory_orchestrator.delete(tenant_id, memory_type, record.key)
                        count += 1
            cleaned[memory_type.value] = count
        return cleaned

    # ------------------------------------------------------------------
    # Background cleanup loop
    # ------------------------------------------------------------------

    async def start_background_cleanup(self, tenant_id: str) -> None:
        """Start periodic cleanup in background."""
        async def _loop() -> None:
            while True:
                await asyncio.sleep(self.CLEANUP_INTERVAL)
                try:
                    result = await self.cleanup_expired(tenant_id)
                    if any(v > 0 for v in result.values()):
                        logger.info(f"Memory cleanup: {result}")
                except Exception as e:
                    logger.warning(f"Memory cleanup failed: {e}")

        self._cleanup_task = asyncio.create_task(_loop())

    async def stop_background_cleanup(self) -> None:
        if self._cleanup_task:
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass


memory_lifecycle = MemoryLifecycle()
