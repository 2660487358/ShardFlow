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

    DEFAULT_TTL_SHORT_TERM = 3600               # 1 hour for session context
    DEFAULT_TTL_SESSION_SUMMARY = 86400 * 7     # 7 days for session summaries
    DEFAULT_TTL_SEMANTIC = 0                    # Permanent for user facts/preferences
    DEFAULT_TTL_EPISODIC = 0                    # Permanent for decision paths/events

    CLEANUP_INTERVAL = 1800                     # Every 30 minutes
    MAX_CLEANUP_PER_TICK = 500                  # Cap per cleanup cycle

    def __init__(self) -> None:
        self._cleanup_task: asyncio.Task[Any] | None = None

    def ttl_for(self, memory_type: MemoryType) -> int:
        mapping = {
            MemoryType.SHORT_TERM: self.DEFAULT_TTL_SHORT_TERM,
            MemoryType.SESSION_SUMMARY: self.DEFAULT_TTL_SESSION_SUMMARY,
            MemoryType.SEMANTIC: self.DEFAULT_TTL_SEMANTIC,
            MemoryType.EPISODIC: self.DEFAULT_TTL_EPISODIC,
        }
        return mapping[memory_type]

    # ------------------------------------------------------------------
    # Create: configure TTL automatically based on memory type
    # ------------------------------------------------------------------

    async def create_record(self, user_id: str, memory_type: MemoryType, key: str,
                            data: dict[str, Any], ttl_seconds: int = 0) -> dict[str, Any]:
        """Create a memory record with auto-TTL if not specified."""
        from app.layers.agent_core.memory_orchestrator import memory_orchestrator

        if ttl_seconds <= 0:
            ttl_seconds = self.ttl_for(memory_type)

        record = await memory_orchestrator.write(user_id, memory_type, key, data, ttl_seconds)
        return record.data

    # ------------------------------------------------------------------
    # Archive: move session data to long-term storage on completion
    # ------------------------------------------------------------------

    async def archive_session(self, user_id: str, session_id: str) -> bool:
        """Archive a SHORT_TERM session to SESSION_SUMMARY.

        S5.7: Emits audit event for archive operation.
        """
        from app.layers.agent_core.memory_orchestrator import memory_orchestrator

        session = await memory_orchestrator.read(user_id, MemoryType.SHORT_TERM, session_id)
        if session is None:
            return False

        task_id = session.data.get("task_id", session_id)
        shard_data = {
            "session_id": session_id,
            "messages": session.data.get("messages", []),
            "summary": session.data.get("summary", ""),
            "archived_at": datetime.now(timezone.utc).isoformat(),
        }
        await memory_orchestrator.write(user_id, MemoryType.SESSION_SUMMARY, task_id, shard_data)
        await memory_orchestrator.delete(user_id, MemoryType.SHORT_TERM, session_id)

        # S5.7: Audit archive operation
        await self._audit_lifecycle_op(
            user_id=user_id,
            operation="archive_session",
            target_id=session_id,
            details={"task_id": task_id, "archived_to": "SESSION_SUMMARY"},
        )
        return True

    # ------------------------------------------------------------------
    # Cleanup: scan all users and memory types for expired entries
    # ------------------------------------------------------------------

    async def cleanup_expired(self) -> int:
        """Scan all Redis memory keys and delete expired records.

        Scans across all users and memory types. Returns total number of
        deleted records.

        S5.7: Emits audit event for batch cleanup operation.
        """
        from app.infrastructure.redis_client import redis_client
        from app.layers.agent_core.memory_orchestrator import memory_orchestrator

        r = await redis_client.get_redis()
        now = datetime.now(timezone.utc)
        deleted_total = 0

        # Pattern: shardflow:{user_id}:mem:{type}:{key}
        prefix = "shardflow:*:mem:*:*"
        try:
            count = 0
            async for key in r.scan_iter(match=prefix, count=50):
                key_str = key.decode() if isinstance(key, bytes) else key
                parts = key_str.split(":")
                if len(parts) < 6:
                    continue
                # parts: shardflow, user_id, mem, type, ...rest
                user_id = parts[1]
                memory_type_str = parts[3]
                record_key = ":".join(parts[4:])

                try:
                    memory_type = MemoryType(memory_type_str)
                except ValueError:
                    continue

                raw = await r.get(key_str)
                if raw is None:
                    continue

                try:
                    import json
                    data = json.loads(raw if isinstance(raw, str) else raw.decode("utf-8"))
                    ttl_seconds = data.get("ttl_seconds", 0)
                    if ttl_seconds <= 0:
                        continue
                    updated_at_str = data.get("updated_at", "")
                    if not updated_at_str:
                        continue
                    updated_at = datetime.fromisoformat(updated_at_str)
                    age = (now - updated_at).total_seconds()
                    if age > ttl_seconds:
                        await memory_orchestrator.delete(user_id, memory_type, record_key)
                        deleted_total += 1
                except Exception:
                    continue

                count += 1
                if count >= self.MAX_CLEANUP_PER_TICK:
                    break
        except Exception as e:
            logger.warning("Cleanup scan failed: %s", e)

        if deleted_total > 0:
            logger.info("Memory cleanup: deleted %d expired records", deleted_total)
            # S5.7: Audit batch cleanup operation
            await self._audit_lifecycle_op(
                user_id="system",
                operation="cleanup_expired",
                target_id="batch",
                details={"deleted_count": deleted_total},
            )
        return deleted_total

    # ------------------------------------------------------------------
    # S5.7: Audit helper for lifecycle operations
    # ------------------------------------------------------------------

    async def _audit_lifecycle_op(self, user_id: str, operation: str,
                                  target_id: str = "",
                                  details: dict[str, Any] | None = None) -> None:
        """S5.7: Audit lifecycle operations (cleanup, archive) per FR-EM-003."""
        try:
            from app.layers.security.audit_logger import audit_logger
            await audit_logger.log(
                event_type=f"memory_{operation}",
                user_id=user_id,
                session_id="",
                task_id="",
                details={
                    "target_memory_id": target_id,
                    "operation": operation,
                    **(details or {}),
                },
                severity="INFO",
            )
        except Exception as e:
            logger.debug("Audit lifecycle op failed (non-blocking): %s", e)

    # ------------------------------------------------------------------
    # Background cleanup loop
    # ------------------------------------------------------------------

    async def start_background_cleanup(self) -> None:
        """Start periodic cleanup for all users in background."""
        async def _loop() -> None:
            while True:
                await asyncio.sleep(self.CLEANUP_INTERVAL)
                try:
                    await self.cleanup_expired()
                except Exception as e:
                    logger.warning("Background memory cleanup failed: %s", e)

        self._cleanup_task = asyncio.create_task(_loop())
        logger.info("Memory lifecycle background cleanup started (interval=%ss)", self.CLEANUP_INTERVAL)

    async def stop_background_cleanup(self) -> None:
        if self._cleanup_task:
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass


memory_lifecycle = MemoryLifecycle()
