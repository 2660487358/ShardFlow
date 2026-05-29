"""L2 Agent Core: MCPClient — Model Context Protocol 客户端。

连接外部 MCP Server（飞书/钉钉/搜索/日历等），支持：
- 工具发现：从 Java kb-mcp 注册中心查询可用 MCP 工具
- 工具调用：通过 MCP 协议执行工具
- 结果解析：标准化 MCP 返回结果
- 连接池管理 + 健康检查
"""
import asyncio
import logging
from dataclasses import dataclass, field
from typing import Any

import httpx

from app.config import settings

logger = logging.getLogger(__name__)


@dataclass
class MCPToolInfo:
    """MCP 工具元数据。"""
    tool_id: str
    tool_name: str
    description: str
    mcp_server_url: str
    input_schema: dict[str, Any] = field(default_factory=dict)
    output_schema: dict[str, Any] = field(default_factory=dict)
    permissions: list[str] = field(default_factory=list)
    version: str = "1.0.0"
    status: str = "ACTIVE"


@dataclass
class MCPCallResult:
    """MCP 工具调用结果。"""
    tool_name: str
    success: bool
    data: Any = None
    error: str = ""
    latency_ms: int = 0


class MCPClient:
    """MCP 协议客户端。

    支持两种工具发现模式：
    1. 动态模式：从 Java kb-mcp 注册中心 API 动态获取
    2. 静态配置模式：从 config.py MCP_SERVERS 字典加载
    """

    def __init__(self) -> None:
        self._http_client: httpx.AsyncClient | None = None
        self._discovered_tools: dict[str, MCPToolInfo] = {}
        self._server_health: dict[str, bool] = {}

    async def _get_client(self) -> httpx.AsyncClient:
        if self._http_client is None:
            self._http_client = httpx.AsyncClient(timeout=httpx.Timeout(30.0))
        return self._http_client

    # ---- 工具发现 ----

    async def discover_tools(self) -> list[MCPToolInfo]:
        """从 Java kb-mcp 注册中心发现所有可用 MCP 工具。

        GET /api/v1/mcp/registry/tools
        """
        base_url = settings.java_base_url
        api_key = settings.java_api_key or settings.llm_api_key
        try:
            client = await self._get_client()
            resp = await client.get(
                f"{base_url}/api/v1/mcp/registry/tools",
                headers={"X-API-Key": api_key},
            )
            resp.raise_for_status()
            data = resp.json()
            tools: list[MCPToolInfo] = []
            for item in data.get("tools", data if isinstance(data, list) else []):
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
                    )
                    tools.append(tool)
                    self._discovered_tools[tool.tool_name] = tool
                except Exception as e:
                    logger.warning(f"Failed to parse MCP tool: {e}")
            logger.info(f"Discovered {len(tools)} MCP tools from registry")
            return tools
        except Exception as e:
            logger.warning(f"Failed to discover MCP tools from Java: {e}")
            return list(self._discovered_tools.values())

    def get_tool(self, tool_name: str) -> MCPToolInfo | None:
        """获取已发现的工具信息。"""
        return self._discovered_tools.get(tool_name)

    def list_tools(self) -> list[MCPToolInfo]:
        """列出所有已发现的工具。"""
        return list(self._discovered_tools.values())

    # ---- 工具调用 ----

    async def call_tool(self, tool_name: str, params: dict[str, Any]) -> MCPCallResult:
        """调用 MCP 工具。

        优先使用已发现的工具信息，如果未发现则尝试从注册中心实时查询。
        """
        import time
        start = time.monotonic()

        tool = self._discovered_tools.get(tool_name)
        if tool is None:
            # 尝试实时发现
            await self.discover_tools()
            tool = self._discovered_tools.get(tool_name)

        if tool is None:
            return MCPCallResult(
                tool_name=tool_name,
                success=False,
                error=f"MCP tool not found: {tool_name}",
            )

        if tool.status != "ACTIVE":
            return MCPCallResult(
                tool_name=tool_name,
                success=False,
                error=f"MCP tool {tool_name} is {tool.status}",
            )

        try:
            client = await self._get_client()
            resp = await client.post(
                f"{tool.mcp_server_url}/tools/call",
                json={
                    "name": tool_name,
                    "arguments": params,
                },
                timeout=httpx.Timeout(60.0),
            )
            latency_ms = int((time.monotonic() - start) * 1000)
            if resp.status_code >= 400:
                return MCPCallResult(
                    tool_name=tool_name,
                    success=False,
                    error=f"MCP server returned {resp.status_code}: {resp.text[:200]}",
                    latency_ms=latency_ms,
                )
            data = resp.json()
            return MCPCallResult(
                tool_name=tool_name,
                success=True,
                data=self._parse_result(tool, data),
                latency_ms=latency_ms,
            )
        except httpx.TimeoutException:
            latency_ms = int((time.monotonic() - start) * 1000)
            return MCPCallResult(
                tool_name=tool_name,
                success=False,
                error=f"MCP call timeout after {latency_ms}ms",
                latency_ms=latency_ms,
            )
        except Exception as e:
            latency_ms = int((time.monotonic() - start) * 1000)
            return MCPCallResult(
                tool_name=tool_name,
                success=False,
                error=f"MCP call failed: {str(e)[:200]}",
                latency_ms=latency_ms,
            )

    def _parse_result(self, tool: MCPToolInfo, raw: dict[str, Any]) -> dict[str, Any]:
        """标准化 MCP 返回结果。"""
        content = raw.get("content", raw.get("result", raw))
        if isinstance(content, list):
            # MCP 标准格式: content: [{type: "text", text: "..."}]
            text_parts = []
            for item in content:
                if isinstance(item, dict) and item.get("type") == "text":
                    text_parts.append(str(item.get("text", "")))
            return {
                "tool_name": tool.tool_name,
                "content": "\n".join(text_parts) if text_parts else str(content),
                "raw": raw,
            }
        return {
            "tool_name": tool.tool_name,
            "content": str(content),
            "raw": raw,
        }

    # ---- 健康检查 ----

    async def check_health(self, tool_name: str) -> bool:
        """检查 MCP 工具是否健康可用。"""
        tool = self._discovered_tools.get(tool_name)
        if tool is None:
            return False
        try:
            client = await self._get_client()
            resp = await client.get(
                f"{tool.mcp_server_url}/health",
                timeout=httpx.Timeout(5.0),
            )
            healthy = resp.status_code == 200
            self._server_health[tool_name] = healthy
            return healthy
        except Exception:
            self._server_health[tool_name] = False
            return False

    async def close(self) -> None:
        if self._http_client:
            await self._http_client.aclose()
            self._http_client = None


mcp_client = MCPClient()
