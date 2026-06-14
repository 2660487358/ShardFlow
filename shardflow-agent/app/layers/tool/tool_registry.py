"""Tool Registry: 内置工具 + MCP 动态发现。

P6 阶段重构 (FR-BUILTIN-002):
- 移除硬编码内置工具（符合 AR-5 红线）
- 内置工具和 MCP 工具统一通过 MCPClient.discover_tools() 发现
- 内置工具的元数据由 Java 端 BuiltinToolInitializer 注册到 MCP 注册中心
- Python 端不再区分 builtin 和 mcp，统一接口

FIX-23: 统一使用 MCPToolInfo 数据模型，避免 MCPToolInfo -> ToolMetadata 转换丢失字段
"""
import logging
from typing import Any

from app.layers.agent_core.mcp_client import MCPToolInfo

logger = logging.getLogger(__name__)


class ToolRegistry:
    """工具注册中心 — 统一发现（内置 + MCP）。"""

    def __init__(self) -> None:
        self._tools: dict[str, MCPToolInfo] = {}
        self._mcp_tools_loaded: bool = False

    def register(self, tool: MCPToolInfo) -> None:
        self._tools[tool.tool_name] = tool

    def get(self, name: str) -> MCPToolInfo:
        if name not in self._tools:
            raise KeyError(f"Tool not found: {name}")
        return self._tools[name]

    def list_all(self) -> list[MCPToolInfo]:
        return list(self._tools.values())

    def validate_input(self, tool_name: str, input_data: dict[str, Any]) -> bool:
        if tool_name not in self._tools:
            return False
        schema = self._tools[tool_name].input_schema
        if not schema:
            return True
        required = schema.get("required", [])
        return all(k in input_data for k in required)

    # ---- 统一工具发现 ----

    async def discover_tools(self) -> list[MCPToolInfo]:
        """从 Java 注册中心动态发现所有工具（含 BUILTIN + MCP）。

        FR-BUILTIN-002: 内置工具与 MCP 工具统一发现，无需区分。
        FIX-23: 直接使用 MCPToolInfo，不再转换为 ToolMetadata，避免字段丢失。
        """
        if self._mcp_tools_loaded:
            return list(self._tools.values())

        try:
            from app.layers.agent_core.mcp_client import mcp_client
            all_tools = await mcp_client.discover_tools()
            for tool_info in all_tools:
                if tool_info.status == "ACTIVE":
                    self._tools[tool_info.tool_name] = tool_info
            self._mcp_tools_loaded = True
            logger.info(f"Tools discovered (builtin + MCP): {len(all_tools)}")
        except Exception as e:
            logger.warning(f"Tool discovery failed: {e}")

        return list(self._tools.values())

    async def refresh_tools(self) -> list[MCPToolInfo]:
        """强制刷新工具列表。"""
        self._tools.clear()
        self._mcp_tools_loaded = False
        return await self.discover_tools()


tool_registry = ToolRegistry()
