"""Memory events — Redis Pub/Sub for cross-process L0 cache invalidation.

Per gap G-6: shard_cache.invalidate() only cleared local L0, no Pub/Sub notification.
This module publishes memory change events so other Python推理层 processes can
invalidate their L0 caches when another process writes.

Channel format: "kb:events:memory:{tenant_id}:{memory_type}"
Message format:  {"action":"write"|"delete","key":"...","version":N}
"""
import asyncio
import json
import logging
from typing import Any

from app.infrastructure.redis_client import redis_client

logger = logging.getLogger(__name__)

CHANNEL_PREFIX = "kb:events:memory"


class MemoryEvents:
    """Publish/subscribe memory change events via Redis Pub/Sub."""

    def __init__(self) -> None:
        self._pubsub: Any = None
        self._listener_task: asyncio.Task[Any] | None = None

    def _channel(self, tenant_id: str, memory_type: str) -> str:
        return f"{CHANNEL_PREFIX}:{tenant_id}:{memory_type}"

    # ------------------------------------------------------------------
    # Publish
    # ------------------------------------------------------------------

    async def publish_write(self, tenant_id: str, memory_type: str, key: str,
                            version: int) -> None:
        """Notify subscribers that a memory record was written."""
        try:
            r = await redis_client.get_redis()
            message = json.dumps({"action": "write", "key": key, "version": version})
            await r.publish(self._channel(tenant_id, memory_type), message)
        except Exception as e:
            logger.warning(f"Failed to publish memory event: {e}")

    async def publish_delete(self, tenant_id: str, memory_type: str, key: str) -> None:
        """Notify subscribers that a memory record was deleted."""
        try:
            r = await redis_client.get_redis()
            message = json.dumps({"action": "delete", "key": key, "version": 0})
            await r.publish(self._channel(tenant_id, memory_type), message)
        except Exception as e:
            logger.warning(f"Failed to publish memory event: {e}")

    # ------------------------------------------------------------------
    # Subscribe (with L0 invalidation callback)
    # ------------------------------------------------------------------

    async def subscribe(self, tenant_id: str, memory_type: str,
                        on_invalidate: Any = None) -> None:
        """Subscribe to memory change events for a tenant+type.

        When an event arrives, calls on_invalidate(tenant_id, memory_type, key)
        so the subscriber can invalidate its L0 cache.
        """
        r = await redis_client.get_redis()
        self._pubsub = r.pubsub()
        channel = self._channel(tenant_id, memory_type)
        await self._pubsub.subscribe(channel)

        async def _listen() -> None:
            try:
                async for message in self._pubsub.listen():
                    if message["type"] != "message":
                        continue
                    try:
                        data = json.loads(message["data"] if isinstance(message["data"], str) else message["data"].decode("utf-8"))
                        key = data.get("key", "")
                        if on_invalidate:
                            await on_invalidate(tenant_id, memory_type, key)
                    except Exception as e:
                        logger.warning(f"Failed to handle memory event: {e}")
            except asyncio.CancelledError:
                await self._pubsub.unsubscribe(channel)

        self._listener_task = asyncio.create_task(_listen())

    # ------------------------------------------------------------------
    # Stop
    # ------------------------------------------------------------------

    async def stop(self) -> None:
        if self._listener_task:
            self._listener_task.cancel()
            try:
                await self._listener_task
            except asyncio.CancelledError:
                pass


memory_events = MemoryEvents()
