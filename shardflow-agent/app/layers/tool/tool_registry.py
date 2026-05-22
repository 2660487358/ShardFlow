"""Tool Registry: 内置工具 + MCP 动态发现。

内置 7 个工具（架构定义），MCP 工具从 Java kb-mcp 注册中心动态发现。
不硬编码 MCP 工具（符合 AR-5 红线）。
"""
import logging
from typing import Any

from app.models.search_result import ToolMetadata

logger = logging.getLogger(__name__)


class ToolRegistry:
    """工具注册中心 — 内置 + MCP 动态发现。"""

    def __init__(self) -> None:
        self._tools: dict[str, ToolMetadata] = {}
        self._mcp_tools_loaded: bool = False

    def register(self, tool: ToolMetadata) -> None:
        self._tools[tool.name] = tool

    def get(self, name: str) -> ToolMetadata:
        if name not in self._tools:
            raise KeyError(f"Tool not found: {name}")
        return self._tools[name]

    def list_all(self) -> list[ToolMetadata]:
        return list(self._tools.values())

    def validate_input(self, tool_name: str, input_data: dict[str, Any]) -> bool:
        if tool_name not in self._tools:
            return False
        schema = self._tools[tool_name].input_schema
        if not schema:
            return True
        required = schema.get("required", [])
        return all(k in input_data for k in required)

    # ---- MCP 动态发现 ----

    async def discover_mcp_tools(self) -> list[ToolMetadata]:
        """从 Java kb-mcp 注册中心动态发现 MCP 工具。

        只在首次调用时加载，后续调用从缓存返回。
        """
        if self._mcp_tools_loaded:
            # 返回当前已注册的 MCP 工具（以 "mcp:" 前缀标识）
            return [t for t in self._tools.values() if t.name.startswith("mcp:")]

        try:
            from app.layers.agent_core.mcp_client import mcp_client
            mcp_tools = await mcp_client.discover_tools()
            for mcp_tool in mcp_tools:
                if mcp_tool.status == "ACTIVE":
                    tool_meta = ToolMetadata(
                        name=f"mcp:{mcp_tool.tool_name}",
                        description=mcp_tool.description,
                        version=mcp_tool.version,
                        input_schema=mcp_tool.input_schema,
                        output_schema=mcp_tool.output_schema,
                        permissions=mcp_tool.permissions,
                    )
                    self._tools[tool_meta.name] = tool_meta
            self._mcp_tools_loaded = True
            logger.info(f"MCP tools discovered: {len(mcp_tools)}")
        except Exception as e:
            logger.warning(f"MCP tool discovery failed: {e}")

        return [t for t in self._tools.values() if t.name.startswith("mcp:")]

    async def refresh_mcp_tools(self) -> list[ToolMetadata]:
        """强制刷新 MCP 工具列表。"""
        # 移除旧的 MCP 工具
        old_mcp = [k for k in self._tools if k.startswith("mcp:")]
        for k in old_mcp:
            del self._tools[k]
        self._mcp_tools_loaded = False
        return await self.discover_mcp_tools()


tool_registry = ToolRegistry()


def _register_default_tools() -> None:
    """注册 7 个内置工具（架构定义）。

    内置工具列表:
    - web_search: 联网搜索（通过 MCP Client）
    - read_file: 读取文件（HTTP 代理到 Java）
    - write_file: 写入文件（HTTP 代理到 Java）
    - code_analyze: 代码分析（HTTP 代理到 Java）
    - extract_shard: 提取状态包快照（内部）
    - query_strategy: 查询历史策略（HTTP 代理到 Java）
    - save_strategy: 保存策略记录（HTTP 代理到 Java）
    """
    defaults = [
        ToolMetadata(
            name="web_search",
            description="联网搜索：通过搜索引擎获取最新信息",
            permissions=["search:read"],
            input_schema={"required": ["query"], "properties": {"query": {"type": "string"}}},
        ),
        ToolMetadata(
            name="read_file",
            description="读取指定文件内容",
            permissions=["repo:read"],
            input_schema={"required": ["path"], "properties": {"path": {"type": "string"}}},
        ),
        ToolMetadata(
            name="write_file",
            description="写入文件内容",
            permissions=["repo:write"],
            input_schema={"required": ["path", "content"], "properties": {"path": {"type": "string"}, "content": {"type": "string"}}},
        ),
        ToolMetadata(
            name="code_analyze",
            description="代码静态分析和语义理解",
            permissions=["repo:read"],
            input_schema={"required": ["path", "query"], "properties": {"path": {"type": "string"}, "query": {"type": "string"}}},
        ),
        ToolMetadata(
            name="extract_shard",
            description="提取 ContextShard 状态包快照",
            permissions=["shard:write"],
        ),
        ToolMetadata(
            name="query_strategy",
            description="查询历史策略记录（语义检索）",
            permissions=["strategy:read"],
            input_schema={"required": ["intent"], "properties": {"intent": {"type": "string"}, "query": {"type": "string"}}},
        ),
        ToolMetadata(
            name="save_strategy",
            description="保存当前策略记录",
            permissions=["strategy:write"],
            input_schema={"required": ["strategy"], "properties": {"strategy": {"type": "object"}}},
        ),
    ]
    for tool in defaults:
        tool_registry.register(tool)


_register_default_tools()
