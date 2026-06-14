"""Memory degradation — graceful fallback when Java peripheral service is unavailable.

Per gap G-7: callback_client.call_with_retry failure was unhandled, no degradation buffer.

Strategy:
1. On Java write failure → buffer to Redis degradation queue
2. Background worker periodically retries failed writes
3. Reads fall back to L1 (Redis) when L2 (Java) is unreachable
"""
import asyncio
import json
import logging
from datetime import datetime, timezone
from typing import Any

from app.infrastructure.redis_client import redis_client

logger = logging.getLogger(__name__)

DEGRADATION_QUEUE_KEY = "shardflow:degradation:write_queue"
RETRY_INTERVAL = 60  # Retry every 60 seconds
MAX_RETRY_AGE = 3600 * 6  # Give up after 6 hours


class MemoryDegradation:
    """Handles graceful degradation when Java L2 backend is unavailable."""

    def __init__(self) -> None:
        self._retry_task: asyncio.Task[Any] | None = None
        self._java_available = True

    # ------------------------------------------------------------------
    # Buffer failed writes
    # ------------------------------------------------------------------

    async def buffer_write(self, user_id: str, memory_type: str, key: str,
                           data: dict[str, Any]) -> None:
        """Buffer a failed write to Redis degradation queue for later retry."""
        r = await redis_client.get_redis()
        entry = json.dumps({
            "user_id": user_id,
            "memory_type": memory_type,
            "key": key,
            "data": data,
            "attempt": 0,
            "buffered_at": datetime.now(timezone.utc).isoformat(),
        }, ensure_ascii=False)
        await r.rpush(DEGRADATION_QUEUE_KEY, entry)
        logger.info(f"Buffered degraded write: {memory_type}/{key}")

    # ------------------------------------------------------------------
    # Check Java availability
    # ------------------------------------------------------------------

    async def check_java_health(self) -> bool:
        """Probe Java service health."""
        try:
            from app.infrastructure.callback_client import callback_client
            await callback_client.write_audit({"event": "health_check", "timestamp": datetime.now(timezone.utc).isoformat()})
            self._java_available = True
            return True
        except Exception:
            self._java_available = False
            return False

    @property
    def java_available(self) -> bool:
        return self._java_available

    # ------------------------------------------------------------------
    # Retry loop: drain degradation queue
    # ------------------------------------------------------------------

    async def _retry_loop(self) -> None:
        """Background loop: drain degradation queue and retry failed writes."""
        while True:
            await asyncio.sleep(RETRY_INTERVAL)
            if not self._java_available:
                await self.check_java_health()
                if not self._java_available:
                    continue

            r = await redis_client.get_redis()
            from app.infrastructure.callback_client import callback_client

            # Process up to 20 entries per tick
            for _ in range(20):
                raw = await r.lpop(DEGRADATION_QUEUE_KEY)
                if raw is None:
                    break

                try:
                    entry = json.loads(raw if isinstance(raw, str) else raw.decode("utf-8"))
                except Exception:
                    continue

                # Check age — discard too-old entries
                try:
                    buffered_at = datetime.fromisoformat(entry.get("buffered_at", ""))
                    age = (datetime.now(timezone.utc) - buffered_at).total_seconds()
                    if age > MAX_RETRY_AGE:
                        logger.warning(f"Discarding stale degraded write: {entry.get('key')}")
                        continue
                except Exception:
                    pass

                entry["attempt"] = entry.get("attempt", 0) + 1
                memory_type = entry.get("memory_type", "")
                key = entry.get("key", "")
                data = entry.get("data", {})

                try:
                    if memory_type == "long_term":
                        await callback_client.session_complete({**data, "task_id": key})
                    elif memory_type == "meta":
                        await callback_client.save_strategy({**data, "strategy_id": key})
                    logger.info(f"Degraded write recovered: {memory_type}/{key}")
                except Exception:
                    if entry["attempt"] < 5:
                        # Re-queue for later retry
                        await r.rpush(DEGRADATION_QUEUE_KEY, json.dumps(entry, ensure_ascii=False))
                    else:
                        logger.error(f"Degraded write exhausted retries: {memory_type}/{key}")

    # ------------------------------------------------------------------
    # Start / Stop
    # ------------------------------------------------------------------

    async def start(self) -> None:
        self._retry_task = asyncio.create_task(self._retry_loop())

    async def stop(self) -> None:
        if self._retry_task:
            self._retry_task.cancel()
            try:
                await self._retry_task
            except asyncio.CancelledError:
                pass


memory_degradation = MemoryDegradation()
