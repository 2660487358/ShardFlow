"""L2 Agent Core: MCPToolCache — MCP 工具 L0 本地缓存 + Redis Hash 状态感知。

实现规格文档 5.3 节定义的工具状态同步机制：
- 启动时 HGETALL 拉取全量工具状态
- 订阅 mcp:wakeup 唤醒信号，收到后立即 HGETALL 刷新
- 30s 定时 HGETALL 轮询兜底
- HGETALL 返回空时降级至 L0 本地缓存 + 告警
- 按分类/标签/关键词筛选工具

P4 增强 (FR-HEALTH-006):
- Hash TTL 过期崩溃检测 → 降级 L0 + 告警
- 降级状态追踪（开始时间、持续时间、连续空拉取次数）
- 降级恢复时自动从 HTTP 补全
"""
import asyncio
import json
import logging
import time
import uuid
from dataclasses import dataclass, field

import httpx
import redis.asyncio as aioredis

from app.config import settings
from app.infrastructure.l0_cache import L0Cache
from app.infrastructure.redis_client import redis_client
from app.layers.agent_core.mcp_client import MCPToolInfo

logger = logging.getLogger(__name__)

# ── 常量 ──────────────────────────────────────────────────────────────────
_POLL_INTERVAL_S = 30  # 定时轮询间隔（秒）
_RECONNECT_DELAY_S = 5  # Pub/Sub 断线重连延迟（秒）
_CONSECUTIVE_EMPTY_THRESHOLD = 3  # 连续空拉取阈值，超过则确认崩溃


@dataclass
class ToolStateInfo:
    """Redis Hash 中单条工具状态记录。"""

    tool_id: str
    status: str  # ACTIVE, INACTIVE, DRAFT
    health: str  # HEALTHY, UNHEALTHY, UNKNOWN
    version: str
    updated_at: str


@dataclass
class DegradationInfo:
    """降级状态信息 (FR-HEALTH-006)。"""

    is_degraded: bool = False
    started_at: float = 0.0  # 降级开始时间戳
    consecutive_empty_pulls: int = 0  # 连续空拉取次数
    last_alert_at: float = 0.0  # 上次告警时间戳
    recovery_count: int = 0  # 累计恢复次数


class MCPToolCache:
    """MCP 工具 L0 本地缓存 + Redis Hash 状态感知。

    三级读取路径中的 L0 层：
    1. L0 本地 LRU 缓存（tool_name → MCPToolInfo）
    2. Redis Hash 状态快照（tool_id → ToolStateInfo）
    3. Java 注册中心 HTTP API（兜底）

    状态同步机制（规格文档 5.3）：
    - 启动回溯：HGETALL 拉取全量
    - 轻量唤醒：订阅 mcp:wakeup → HGETALL
    - 定时轮询：30s HGETALL 兜底
    - 降级：HGETALL 空 → L0 缓存 + 告警
    """

    def __init__(self) -> None:
        self._l0_cache: L0Cache = L0Cache(max_size=256)
        self._tool_states: dict[str, ToolStateInfo] = {}
        self._user_id: str = ""
        self._redis: aioredis.Redis | None = None
        self._pubsub_task: asyncio.Task | None = None
        self._poll_task: asyncio.Task | None = None
        self._degradation: DegradationInfo = DegradationInfo()
        self._snapshot_version: str = ""

    # ── 生命周期 ──────────────────────────────────────────────────────────

    async def start(self, user_id: str) -> None:
        """启动缓存：初始拉取 + 唤醒订阅 + 定时轮询。"""
        self._user_id = user_id
        self._snapshot_version = uuid.uuid4().hex[:8]

        # 初始拉取
        await self._pull_from_hash()

        # 如果初始 HGETALL 返回空，回退到 HTTP discover API
        if not self._tool_states:
            logger.warning(
                "[MCPToolCache] Redis Hash 为空，回退到 HTTP discover API 拉取工具"
            )
            await self._fetch_from_http()

        # 启动后台任务
        self._pubsub_task = asyncio.create_task(
            self._subscribe_wakeup(), name="mcp-tool-cache-pubsub"
        )
        self._poll_task = asyncio.create_task(
            self._poll_loop(), name="mcp-tool-cache-poll"
        )
        logger.info(
            "[MCPToolCache] 已启动 user=%s degraded=%s tools=%d",
            user_id,
            self._degradation.is_degraded,
            len(self._l0_cache),
        )

    async def stop(self) -> None:
        """停止缓存：取消后台任务 + 关闭连接。"""
        for task in (self._pubsub_task, self._poll_task):
            if task and not task.done():
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
        self._pubsub_task = None
        self._poll_task = None

        # 关闭 pubsub 连接
        if self._redis:
            try:
                await self._redis.aclose()
            except Exception:
                pass
            self._redis = None

        logger.info("[MCPToolCache] 已停止 user=%s", self._user_id)

    # ── Redis Hash 拉取 ──────────────────────────────────────────────────

    async def _pull_from_hash(self) -> None:
        """从 Redis Hash 拉取全量工具状态。

        HGETALL shardflow:{user_id}:mcp:tool_states
        - 空 → 降级至 L0 缓存 + 告警 (FR-HEALTH-006 崩溃检测)
        - 非空 → 解析 ToolStateInfo，对 ACTIVE 且不在 L0 的工具从 HTTP 补全
        """
        hash_key = f"shardflow:{self._user_id}:mcp:tool_states"
        try:
            r = await redis_client.get_redis()
            raw: dict = await r.hgetall(hash_key)  # type: ignore[assignment]

            if not raw:
                # FR-HEALTH-006: Hash TTL 过期 → 崩溃检测
                self._handle_empty_hash(hash_key)
                return

            # 解析每条工具状态
            new_states: dict[str, ToolStateInfo] = {}
            active_tool_ids_missing_l0: list[str] = []

            for field, value in raw.items():
                # aioredis 可能返回 bytes 或 str，统一处理
                tool_id = (
                    field.decode() if isinstance(field, bytes) else field
                )
                value_str = (
                    value.decode() if isinstance(value, bytes) else value
                )
                try:
                    obj = json.loads(value_str)
                    state = ToolStateInfo(
                        tool_id=tool_id,
                        status=obj.get("status", "UNKNOWN"),
                        health=obj.get("health", "UNKNOWN"),
                        version=obj.get("version", ""),
                        updated_at=obj.get("updated_at", ""),
                    )
                    new_states[tool_id] = state

                    if state.status == "ACTIVE":
                        # 检查 L0 缓存中是否有该工具的完整元数据
                        if not self._find_tool_by_id_in_l0(tool_id):
                            active_tool_ids_missing_l0.append(tool_id)
                except (json.JSONDecodeError, KeyError) as e:
                    logger.warning(
                        "[MCPToolCache] 解析工具状态失败 tool_id=%s: %s",
                        tool_id,
                        e,
                    )

            self._tool_states = new_states

            # 从降级中恢复
            if self._degradation.is_degraded:
                self._handle_recovery()

            # 对 ACTIVE 但 L0 缺失的工具，从 Java discover API 补全
            if active_tool_ids_missing_l0:
                logger.info(
                    "[MCPToolCache] %d 个 ACTIVE 工具不在 L0 缓存，"
                    "从 HTTP discover API 补全",
                    len(active_tool_ids_missing_l0),
                )
                await self._fetch_from_http()

            # 移除 L0 中状态已变为 INACTIVE/DRAFT 的工具
            active_ids = {
                s.tool_id
                for s in self._tool_states.values()
                if s.status == "ACTIVE"
            }
            for tool_name in list(self._list_l0_tool_names()):
                tool = self._l0_cache.get(tool_name)
                if tool and tool.tool_id not in active_ids:
                    self._l0_cache.invalidate(tool_name)

            self._snapshot_version = uuid.uuid4().hex[:8]
            logger.debug(
                "[MCPToolCache] HGETALL 刷新完成 states=%d", len(new_states)
            )

        except Exception as e:
            logger.warning(
                "[MCPToolCache] HGETALL 异常 (key=%s): %s", hash_key, e
            )
            if not self._degradation.is_degraded:
                logger.warning(
                    "[MCPToolCache] Redis 异常，降级至 L0 本地缓存"
                )
                self._degradation.is_degraded = True
                self._degradation.started_at = time.time()
                self._degradation.consecutive_empty_pulls += 1

    def _handle_empty_hash(self, hash_key: str) -> None:
        """FR-HEALTH-006: Hash TTL 过期崩溃检测处理.

        Hash 为空意味着 Java 端心跳停止（Java 进程崩溃或重启），
        Hash TTL 30s 自动过期后 HGETALL 返回空。
        """
        self._degradation.consecutive_empty_pulls += 1

        if not self._degradation.is_degraded:
            # 首次检测到空 Hash
            self._degradation.is_degraded = True
            self._degradation.started_at = time.time()
            logger.warning(
                "[MCPToolCache] [CRASH-DETECT] HGETALL 返回空 (key=%s)，"
                "Java 注册中心可能已崩溃（Hash TTL 过期），降级至 L0 本地缓存",
                hash_key,
            )
        else:
            # 持续降级中，周期性告警
            duration_s = time.time() - self._degradation.started_at
            now = time.time()
            # 每 60 秒告警一次
            if now - self._degradation.last_alert_at > 60:
                self._degradation.last_alert_at = now
                logger.warning(
                    "[MCPToolCache] [CRASH-DETECT] Java 注册中心持续不可用 "
                    "(duration=%.0fs, consecutive_empty=%d)，"
                    "继续使用 L0 本地缓存降级运行",
                    duration_s,
                    self._degradation.consecutive_empty_pulls,
                )

        # 连续空拉取超过阈值，确认崩溃，尝试 HTTP 兜底
        if (
            self._degradation.consecutive_empty_pulls
            >= _CONSECUTIVE_EMPTY_THRESHOLD
        ):
            logger.warning(
                "[MCPToolCache] [CRASH-DETECT] 连续 %d 次 HGETALL 为空，"
                "确认 Java 注册中心崩溃，尝试 HTTP discover API 兜底",
                self._degradation.consecutive_empty_pulls,
            )
            # 异步触发 HTTP 兜底（不阻塞当前拉取流程）
            asyncio.create_task(self._fetch_from_http())

    def _handle_recovery(self) -> None:
        """从降级状态恢复."""
        duration_s = time.time() - self._degradation.started_at
        self._degradation.recovery_count += 1
        logger.info(
            "[MCPToolCache] [RECOVERY] Java 注册中心恢复 "
            "(降级持续 %.0fs, 累计恢复 %d 次)，"
            "从降级模式恢复正常",
            duration_s,
            self._degradation.recovery_count,
        )
        self._degradation.is_degraded = False
        self._degradation.started_at = 0.0
        self._degradation.consecutive_empty_pulls = 0

    # ── Pub/Sub 唤醒订阅 ─────────────────────────────────────────────────

    async def _subscribe_wakeup(self) -> None:
        """订阅 mcp:wakeup 通道，收到信号后立即 HGETALL 刷新。

        断线时自动重连，重连间隔 %d 秒。
        """ % _RECONNECT_DELAY_S
        channel = f"shardflow:{self._user_id}:mcp:wakeup"
        while True:
            pubsub = None
            try:
                r = await redis_client.get_redis()
                pubsub = r.pubsub()
                await pubsub.subscribe(channel)
                logger.info("[MCPToolCache] 已订阅唤醒通道: %s", channel)

                async for message in pubsub.listen():
                    if message["type"] == "message":
                        logger.debug(
                            "[MCPToolCache] 收到唤醒信号，执行 HGETALL 刷新"
                        )
                        await self._pull_from_hash()

            except asyncio.CancelledError:
                if pubsub:
                    try:
                        await pubsub.unsubscribe(channel)
                        await pubsub.aclose()
                    except Exception:
                        pass
                logger.info("[MCPToolCache] Pub/Sub 订阅已取消")
                return

            except Exception as e:
                logger.warning(
                    "[MCPToolCache] Pub/Sub 异常 (channel=%s): %s，"
                    "%d 秒后重连",
                    channel,
                    e,
                    _RECONNECT_DELAY_S,
                )
                if pubsub:
                    try:
                        await pubsub.aclose()
                    except Exception:
                        pass

            # 重连等待
            try:
                await asyncio.sleep(_RECONNECT_DELAY_S)
            except asyncio.CancelledError:
                return

    # ── 定时轮询 ─────────────────────────────────────────────────────────

    async def _poll_loop(self) -> None:
        """30 秒定时 HGETALL 轮询兜底，防止唤醒信号丢失。"""
        while True:
            try:
                await asyncio.sleep(_POLL_INTERVAL_S)
                await self._pull_from_hash()
            except asyncio.CancelledError:
                logger.info("[MCPToolCache] 轮询任务已取消")
                return
            except Exception as e:
                logger.warning("[MCPToolCache] 轮询异常: %s", e)

    # ── HTTP 兜底 ────────────────────────────────────────────────────────

    async def _fetch_from_http(self) -> None:
        """回退到 Java discover API 拉取工具元数据，填充 L0 缓存。"""
        base_url = settings.java_base_url
        api_key = settings.java_api_key
        url = f"{base_url}/api/v1/mcp/registry/tools/discover"
        headers: dict[str, str] = {
            "X-API-Key": api_key,
            "X-User-Id": self._user_id,
        }
        try:
            async with httpx.AsyncClient(
                timeout=httpx.Timeout(15.0)
            ) as client:
                resp = await client.get(url, headers=headers)
                resp.raise_for_status()
                data = resp.json()

            tools_raw = data.get("tools", data if isinstance(data, list) else [])
            count = 0
            for item in tools_raw:
                try:
                    tool = MCPToolInfo(
                        tool_id=item.get("tool_id", ""),
                        tool_name=item.get("tool_name", ""),
                        description=item.get("description", ""),
                        mcp_server_url=item.get("mcp_server_url", ""),
                        input_schema=item.get("input_schema", {}),
                        output_schema=item.get("output_schema", {}),
                        permissions=item.get("permissions", []),
                        version=item.get("version", "1.0.0"),
                        status=item.get("status", "ACTIVE"),
                        category=item.get("category", "other"),
                        tags=item.get("tags", []),
                    )
                    if tool.status == "ACTIVE":
                        self._l0_cache.set(tool.tool_name, tool)
                        count += 1
                except Exception as e:
                    logger.warning(
                        "[MCPToolCache] HTTP 解析工具失败: %s", e
                    )

            self._snapshot_version = uuid.uuid4().hex[:8]
            logger.info(
                "[MCPToolCache] HTTP discover 补全完成，写入 %d 个 ACTIVE 工具",
                count,
            )

        except Exception as e:
            logger.warning(
                "[MCPToolCache] HTTP discover API 调用失败 (%s): %s", url, e
            )

    # ── 公开查询接口 ─────────────────────────────────────────────────────

    def get_tool(self, tool_name: str) -> MCPToolInfo | None:
        """从 L0 缓存获取工具元数据。"""
        return self._l0_cache.get(tool_name)

    def list_tools(self) -> list[MCPToolInfo]:
        """列出 L0 缓存中所有 ACTIVE 工具。"""
        result: list[MCPToolInfo] = []
        for name in self._list_l0_tool_names():
            tool = self._l0_cache.get(name)
            if tool and tool.status == "ACTIVE":
                result.append(tool)
        return result

    def filter_tools(
        self,
        category: str | None = None,
        tags: list[str] | None = None,
        keyword: str | None = None,
    ) -> list[MCPToolInfo]:
        """按分类/标签/关键词筛选 ACTIVE 工具。

        Args:
            category: 按分类精确匹配
            tags: 按标签任意匹配（OR 语义）
            keyword: 在 tool_name 和 description 中搜索

        Returns:
            符合所有筛选条件的 ACTIVE 工具列表
        """
        result: list[MCPToolInfo] = []
        keyword_lower = keyword.lower() if keyword else None

        for name in self._list_l0_tool_names():
            tool = self._l0_cache.get(name)
            if not tool or tool.status != "ACTIVE":
                continue

            # 分类精确匹配
            if category and tool.category != category:
                continue

            # 标签任意匹配
            if tags and not any(t in tool.tags for t in tags):
                continue

            # 关键词搜索（tool_name + description）
            if keyword_lower:
                searchable = f"{tool.tool_name} {tool.description}".lower()
                if keyword_lower not in searchable:
                    continue

            result.append(tool)

        return result

    def get_tool_state(self, tool_id: str) -> ToolStateInfo | None:
        """从 Redis Hash 状态快照获取工具状态。"""
        return self._tool_states.get(tool_id)

    def is_degraded(self) -> bool:
        """是否处于降级模式（Java 注册中心不可用）(FR-HEALTH-006)."""
        return self._degradation.is_degraded

    def get_degradation_info(self) -> DegradationInfo:
        """获取降级状态详情 (FR-HEALTH-006)."""
        return self._degradation

    def get_snapshot_version(self) -> str:
        """获取当前快照版本号。"""
        return self._snapshot_version

    # ── 内部辅助 ─────────────────────────────────────────────────────────

    def _list_l0_tool_names(self) -> list[str]:
        """列出 L0 缓存中所有 key（tool_name）。"""
        return self._l0_cache.keys()

    def _find_tool_by_id_in_l0(self, tool_id: str) -> MCPToolInfo | None:
        """在 L0 缓存中按 tool_id 查找工具。"""
        for name in self._list_l0_tool_names():
            tool = self._l0_cache.get(name)
            if tool and tool.tool_id == tool_id:
                return tool
        return None


# ── 模块级单例 ────────────────────────────────────────────────────────────
mcp_tool_cache = MCPToolCache()
