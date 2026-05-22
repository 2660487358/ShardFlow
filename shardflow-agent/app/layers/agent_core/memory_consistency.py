"""Memory consistency — unified optimistic lock, version control, conflict detection, merge.

Integrates existing optimistic_lock (Redis Lua CAS) with context_shard.check_conflict/merge_shard
to provide a single entry point for memory consistency operations.

Per gap G-5: optimistic_lock was independent, not linked with conflict detection.
"""
import logging
from typing import Any

from app.infrastructure.optimistic_lock import optimistic_lock
from app.layers.agent_core.context_shard import context_shard_manager
from app.models.context_shard import ContextShard

logger = logging.getLogger(__name__)


class MemoryConsistency:
    """Unified memory consistency: CAS version control + conflict detection + merge."""

    MAX_CAS_RETRIES = 3

    async def write_with_cas(self, user_id: str, task_id: str,
                             shard_data: dict[str, Any]) -> dict[str, Any]:
        """Write shard with CAS version check via Redis Lua script.

        Returns the written shard_data with updated version on success.
        Raises ValueError if CAS fails after max retries (conflict).
        """
        return await optimistic_lock.save_with_version_check(user_id, task_id, shard_data)

    async def acquire_lock(self, user_id: str, task_id: str) -> bool:
        """Acquire distributed lock before merging shards."""
        return await optimistic_lock.acquire(user_id, task_id)

    async def release_lock(self, user_id: str, task_id: str) -> None:
        await optimistic_lock.release(user_id, task_id)

    async def check_and_merge(self, current_data: dict[str, Any],
                              previous_data: dict[str, Any],
                              user_decision: str = "AUTO_MERGE") -> dict[str, Any]:
        """Check conflict between current and previous shard, then merge.

        Args:
            current_data: The new shard data being written.
            previous_data: The existing shard data from L2.
            user_decision: "AUTO_MERGE", "KEEP_PREVIOUS", or "ACCEPT_CURRENT".

        Returns:
            The merged shard data dict.
        """
        try:
            current = ContextShard(**current_data)
            previous = ContextShard(**previous_data)
        except Exception as e:
            logger.warning(f"Failed to parse shards for merge: {e}")
            return current_data  # Fallback: accept current

        conflicts = context_shard_manager.check_conflict(current, previous)
        if conflicts:
            logger.info(f"Conflicts detected during merge: {[c.conflict_type for c in conflicts]}")

        merged = context_shard_manager.merge_shard(current, previous, user_decision)
        return merged.model_dump()

    async def get_version(self, user_id: str, task_id: str) -> int:
        return await optimistic_lock.get_version(user_id, task_id)


memory_consistency = MemoryConsistency()
