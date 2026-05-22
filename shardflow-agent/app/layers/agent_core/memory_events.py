"""Memory events — Redis Pub/Sub for cross-process L0 cache invalidation.

Per gap G-6: shard_cache.invalidate() only cleared local L0, no Pub/Sub notification.
This module publishes memory change events so other Python 推理层 processes can
invalidate their L0 caches when another process writes.

Channel format: "shardflow:events:memory:{user_id}:{memory_type}"
Message format:  {"action":"write"|"delete","key":"...","version":N}

--- 业务事件（v2 新增） ---

5 种业务事件类型，发布到统一的 "shardflow:{user_id}:events" 频道：
- shard_created:        ContextShard 提取完成
- session_completed:    会话结束
- strategy_updated:     策略更新
- profile_updated:      画像变更 → 使 ProfileSearcher 缓存失效
- mcp_tool_status_changed: MCP 工具状态变更 → 刷新 ToolRegistry
"""
import asyncio
import json
import logging
from typing import Any, Callable, Awaitable

from app.infrastructure.redis_client import redis_client

logger = logging.getLogger(__name__)

CHANNEL_PREFIX = "shardflow:events:memory"
BUSINESS_EVENTS_CHANNEL = "shardflow:{user_id}:events"

# 5 种业务事件类型
VALID_BUSINESS_EVENT_TYPES = frozenset({
    "shard_created",
    "session_completed",
    "strategy_updated",
    "profile_updated",
    "mcp_tool_status_changed",
})


class MemoryEvents:
    """Publish/subscribe memory change events via Redis Pub/Sub."""

    def __init__(self) -> None:
        self._pubsub: Any = None
        self._listener_task: asyncio.Task[Any] | None = None

    def _channel(self, user_id: str, memory_type: str) -> str:
        return f"{CHANNEL_PREFIX}:{user_id}:{memory_type}"

    # ------------------------------------------------------------------
    # Publish
    # ------------------------------------------------------------------

    async def publish_write(self, user_id: str, memory_type: str, key: str,
                            version: int) -> None:
        """Notify subscribers that a memory record was written."""
        try:
            r = await redis_client.get_redis()
            message = json.dumps({"action": "write", "key": key, "version": version})
            await r.publish(self._channel(user_id, memory_type), message)
        except Exception as e:
            logger.warning(f"Failed to publish memory event: {e}")

    async def publish_delete(self, user_id: str, memory_type: str, key: str) -> None:
        """Notify subscribers that a memory record was deleted."""
        try:
            r = await redis_client.get_redis()
            message = json.dumps({"action": "delete", "key": key, "version": 0})
            await r.publish(self._channel(user_id, memory_type), message)
        except Exception as e:
            logger.warning(f"Failed to publish memory event: {e}")

    # ------------------------------------------------------------------
    # Subscribe (with L0 invalidation callback)
    # ------------------------------------------------------------------

    async def subscribe(self, user_id: str, memory_type: str,
                        on_invalidate: Any = None) -> None:
        """Subscribe to memory change events for a user+type.

        When an event arrives, calls on_invalidate(user_id, memory_type, key)
        so the subscriber can invalidate its L0 cache.
        """
        r = await redis_client.get_redis()
        self._pubsub = r.pubsub()
        channel = self._channel(user_id, memory_type)
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
                            await on_invalidate(user_id, memory_type, key)
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


# ══════════════════════════════════════════════════════════════════════════════
# BusinessEvents — 业务事件 Pub/Sub（v2 新增，对应需求 5-05/US-216）
# ══════════════════════════════════════════════════════════════════════════════

HandlerFunc = Callable[[str, str, dict[str, Any]], Awaitable[None]]
"""事件处理回调: async (user_id, event_type, payload) -> None"""


class BusinessEvents:
    """业务事件发布/订阅 — 5 种跨进程事件通知。

    频道模式: kb:{user_id}:events
    消息格式: {"event_type": "profile_updated", "payload": {"user_id": "...", ...}, "timestamp": "ISO8601"}
    """

    MAX_RECONNECT_DELAY = 60.0  # 最大重连间隔（秒）

    def __init__(self) -> None:
        self._pubsub: Any = None
        self._listener_task: asyncio.Task[Any] | None = None
        self._handlers: dict[str, list[HandlerFunc]] = {
            et: [] for et in VALID_BUSINESS_EVENT_TYPES
        }
        self._running = False

    # ------------------------------------------------------------------
    # Handler Registration
    # ------------------------------------------------------------------

    def on(self, event_type: str, handler: HandlerFunc) -> None:
        """注册事件处理器。"""
        if event_type not in self._handlers:
            logger.warning(f"Unknown event type: {event_type}, valid: {sorted(VALID_BUSINESS_EVENT_TYPES)}")
            return
        self._handlers[event_type].append(handler)
        logger.debug(f"Registered handler for {event_type}")

    def off(self, event_type: str, handler: HandlerFunc) -> None:
        """移除事件处理器。"""
        if event_type in self._handlers:
            try:
                self._handlers[event_type].remove(handler)
            except ValueError:
                pass

    # ------------------------------------------------------------------
    # Publish
    # ------------------------------------------------------------------

    async def publish(self, user_id: str, event_type: str,
                      payload: dict[str, Any]) -> bool:
        """发布业务事件。

        Args:
            user_id: 用户 ID
            event_type: 事件类型（必须是 5 种有效类型之一）
            payload: 事件负载（自动注入 user_id 和 timestamp）

        Returns:
            是否发布成功
        """
        if event_type not in VALID_BUSINESS_EVENT_TYPES:
            logger.warning(f"Invalid business event type: {event_type}")
            return False

        import time
        message = json.dumps({
            "event_type": event_type,
            "payload": {**payload, "user_id": user_id},
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        })

        channel = BUSINESS_EVENTS_CHANNEL.format(user_id=user_id)
        try:
            r = await redis_client.get_redis()
            await r.publish(channel, message)
            logger.debug(f"Published {event_type} for user={user_id}")
            return True
        except Exception as e:
            logger.warning(f"Failed to publish {event_type} for user={user_id}: {e}")
            return False

    # ------------------------------------------------------------------
    # Subscribe
    # ------------------------------------------------------------------

    async def subscribe(self, user_id: str) -> None:
        """订阅用户的所有业务事件。

        启动后台监听任务，收到事件时分发到注册的处理器。
        支持自动重连（指数退避，最大 {MAX_RECONNECT_DELAY}s）。
        """
        self._running = True
        self._listener_task = asyncio.create_task(self._listen_loop(user_id))
        logger.info(f"BusinessEvents subscribed for user={user_id}")

    async def _listen_loop(self, user_id: str) -> None:
        """后台事件监听循环（含自动重连）。"""
        channel = BUSINESS_EVENTS_CHANNEL.format(user_id=user_id)
        reconnect_delay = 1.0

        while self._running:
            try:
                r = await redis_client.get_redis()
                self._pubsub = r.pubsub()
                await self._pubsub.subscribe(channel)
                reconnect_delay = 1.0  # 连接成功后重置退避

                async for message in self._pubsub.listen():
                    if not self._running:
                        break
                    if message["type"] != "message":
                        continue
                    try:
                        data = json.loads(
                            message["data"] if isinstance(message["data"], str)
                            else message["data"].decode("utf-8")
                        )
                        event_type = data.get("event_type", "")
                        payload = data.get("payload", {})
                        await self._dispatch(user_id, event_type, payload)
                    except json.JSONDecodeError:
                        logger.warning(f"Invalid business event JSON: {message.get('data', '')[:100]}")
                    except Exception as e:
                        logger.warning(f"Failed to handle business event: {e}")

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.warning(
                    f"BusinessEvents connection lost for user={user_id}: {e}. "
                    f"Reconnecting in {reconnect_delay:.0f}s..."
                )
                await asyncio.sleep(reconnect_delay)
                reconnect_delay = min(reconnect_delay * 2, self.MAX_RECONNECT_DELAY)

        # Cleanup
        try:
            if self._pubsub:
                await self._pubsub.unsubscribe(channel)
        except Exception:
            pass

    async def _dispatch(self, user_id: str, event_type: str,
                        payload: dict[str, Any]) -> None:
        """分发事件到注册的处理器。"""
        handlers = self._handlers.get(event_type, [])
        if not handlers:
            return

        for handler in handlers:
            try:
                await handler(user_id, event_type, payload)
            except Exception as e:
                logger.warning(
                    f"Handler {handler.__name__} failed for {event_type}: {e}"
                )

    # ------------------------------------------------------------------
    # Stop
    # ------------------------------------------------------------------

    async def stop(self) -> None:
        """停止事件监听。"""
        self._running = False
        if self._listener_task:
            self._listener_task.cancel()
            try:
                await self._listener_task
            except asyncio.CancelledError:
                pass
            self._listener_task = None
        logger.info("BusinessEvents stopped")


# ------------------------------------------------------------------
# Built-in Event Handlers
# ------------------------------------------------------------------

async def _on_profile_updated(user_id: str, event_type: str,
                               payload: dict[str, Any]) -> None:
    """画像更新 → 使 ProfileSearcher 缓存失效。"""
    try:
        from app.layers.retrieval.profile_searcher import profile_searcher
        await profile_searcher.invalidate_cache(user_id)
        logger.info(f"Profile cache invalidated for user={user_id} via Pub/Sub")
    except Exception as e:
        logger.warning(f"Failed to invalidate profile cache: {e}")


async def _on_mcp_tool_status_changed(user_id: str, event_type: str,
                                       payload: dict[str, Any]) -> None:
    """MCP 工具状态变更 → 刷新 ToolRegistry MCP 工具列表。"""
    try:
        from app.layers.tool.tool_registry import tool_registry
        await tool_registry.refresh_mcp_tools()
        logger.info(f"MCP tools refreshed via Pub/Sub event")
    except Exception as e:
        logger.warning(f"Failed to refresh MCP tools: {e}")


async def _on_shard_created(user_id: str, event_type: str,
                             payload: dict[str, Any]) -> None:
    """ContextShard 创建 → 日志记录。"""
    task_id = payload.get("task_id", "unknown")
    logger.info(f"Shard created: user={user_id}, task={task_id}")


async def _on_session_completed(user_id: str, event_type: str,
                                 payload: dict[str, Any]) -> None:
    """会话完成 → 日志记录。"""
    task_id = payload.get("task_id", "unknown")
    logger.info(f"Session completed: user={user_id}, task={task_id}")


async def _on_strategy_updated(user_id: str, event_type: str,
                                payload: dict[str, Any]) -> None:
    """策略更新 → 日志记录（后续可扩展：刷新本地策略缓存）。"""
    strategy_id = payload.get("strategy_id", "unknown")
    logger.info(f"Strategy updated: user={user_id}, strategy={strategy_id}")


# 全局单例，启动时自动注册内置处理器
business_events = BusinessEvents()
business_events.on("profile_updated", _on_profile_updated)
business_events.on("mcp_tool_status_changed", _on_mcp_tool_status_changed)
business_events.on("shard_created", _on_shard_created)
business_events.on("session_completed", _on_session_completed)
business_events.on("strategy_updated", _on_strategy_updated)
