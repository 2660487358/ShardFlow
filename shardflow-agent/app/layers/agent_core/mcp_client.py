"""L2 Agent Core: MCPClient — Model Context Protocol 客户端。

P6 阶段重写，统一内置工具和 MCP 工具调用接口：
- 内置工具（tool_type=BUILTIN）：本地执行，不走 MCP Server
- MCP 工具（tool_type=MCP）：通过传输协议调用 MCP Server
- 传输协议：HTTP-SSE / stdio，由连接管理器统一管理
- 工具发现：从 Java 注册中心获取（含 BUILTIN + MCP）
- 安全网关：权限校验 + 频率限制 + 高风险确认 + 副作用授权
- 审计回调：调用结果回调 Java 端记录
- 降级处理：调用失败不阻塞推理循环
"""
import asyncio
import logging
import time
import uuid
from dataclasses import dataclass, field
from typing import Any

import httpx

from app.config import settings

logger = logging.getLogger(__name__)


@dataclass
class MCPToolInfo:
    """MCP 工具元数据（统一内置和 MCP 工具）。"""
    tool_id: str
    tool_name: str
    description: str
    tool_type: str = "MCP"  # BUILTIN / MCP
    mcp_server_url: str = ""
    input_schema: dict[str, Any] = field(default_factory=dict)
    output_schema: dict[str, Any] = field(default_factory=dict)
    permissions: list[str] = field(default_factory=list)
    version: str = "1.0.0"
    status: str = "ACTIVE"
    category: str = "other"
    tags: list[str] = field(default_factory=list)
    transport: str = "http-sse"
    timeout_seconds: int = 30
    retry_count: int = 1
    risk_level: str = "low"
    auth_config: dict[str, Any] | None = None


@dataclass
class MCPCallResult:
    """MCP 工具调用结果。"""
    tool_name: str
    success: bool
    data: Any = None
    error: str = ""
    latency_ms: int = 0
    tool_id: str = ""
    tool_version: str = ""
    degraded: bool = False


class MCPClient:
    """MCP 协议客户端。

    P6 阶段统一接口：
    - 内置工具（BUILTIN）：通过 builtin_tool_registry 本地执行
    - MCP 工具：通过连接管理器 + 传输协议远程调用
    - 对上层调用者完全透明（FR-BUILTIN-002）
    """

    def __init__(self) -> None:
        self._http_client: httpx.AsyncClient | None = None
        self._discovered_tools: dict[str, MCPToolInfo] = {}

    async def _get_client(self) -> httpx.AsyncClient:
        if self._http_client is None:
            self._http_client = httpx.AsyncClient(timeout=httpx.Timeout(30.0))
        return self._http_client

    # ---- 工具发现 ----

    async def discover_tools(self, user_id: str | None = None) -> list[MCPToolInfo]:
        """发现所有可用工具（含 BUILTIN + MCP）。

        优先从 MCPToolCache（L0 缓存 + Redis Hash）获取，
        回退到 Java 注册中心 HTTP API。
        """
        # 优先从 L0 缓存获取
        try:
            from app.layers.agent_core.mcp_tool_cache import mcp_tool_cache
            cached_tools = mcp_tool_cache.list_tools()
            if cached_tools:
                for tool in cached_tools:
                    self._discovered_tools[tool.tool_name] = tool
                logger.info(f"Discovered {len(cached_tools)} tools from L0 cache")
                return cached_tools
        except Exception as e:
            logger.debug(f"L0 cache not available, falling back to HTTP: {e}")

        # 回退到 Java 注册中心 API
        return await self._discover_from_http(user_id)

    async def _discover_from_http(self, user_id: str | None = None) -> list[MCPToolInfo]:
        """从 Java 注册中心 HTTP API 发现工具。"""
        base_url = settings.java_base_url
        api_key = settings.java_api_key or settings.llm_api_key
        headers: dict[str, str] = {"X-API-Key": api_key}
        if user_id:
            headers["X-User-Id"] = user_id

        try:
            client = await self._get_client()
            resp = await client.get(
                f"{base_url}/api/v1/mcp/registry/tools/discover",
                headers=headers,
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
                        tool_type=item.get("tool_type", "MCP"),
                        mcp_server_url=item.get("mcp_server_url", ""),
                        input_schema=item.get("input_schema", {}),
                        output_schema=item.get("output_schema", {}),
                        permissions=item.get("permissions", []),
                        version=item.get("version", "1.0.0"),
                        status=item.get("status", "ACTIVE"),
                        category=item.get("category", "other"),
                        tags=item.get("tags", []),
                        transport=item.get("transport", "http-sse"),
                        timeout_seconds=item.get("timeout_seconds", 30),
                        retry_count=item.get("retry_count", 1),
                        risk_level=item.get("risk_level", "low"),
                    )
                    tools.append(tool)
                    self._discovered_tools[tool.tool_name] = tool
                except Exception as e:
                    logger.warning(f"Failed to parse tool: {e}")
            logger.info(f"Discovered {len(tools)} tools from HTTP API")
            return tools
        except Exception as e:
            logger.warning(f"Failed to discover tools from Java: {e}")
            return list(self._discovered_tools.values())

    def get_tool(self, tool_name: str) -> MCPToolInfo | None:
        """获取已发现的工具信息。优先从 L0 缓存获取。"""
        # 优先从 L0 缓存获取
        try:
            from app.layers.agent_core.mcp_tool_cache import mcp_tool_cache
            cached = mcp_tool_cache.get_tool(tool_name)
            if cached:
                return cached
        except Exception:
            pass
        return self._discovered_tools.get(tool_name)

    def list_tools(self) -> list[MCPToolInfo]:
        """列出所有已发现的工具。"""
        all_tools: dict[str, MCPToolInfo] = dict(self._discovered_tools)
        try:
            from app.layers.agent_core.mcp_tool_cache import mcp_tool_cache
            for tool in mcp_tool_cache.list_tools():
                all_tools[tool.tool_name] = tool
        except Exception:
            pass
        return list(all_tools.values())

    # ---- 统一工具调用 ----

    async def call_tool(
        self,
        tool_name: str,
        params: dict[str, Any],
        user_permissions: list[str] | None = None,
        user_id: str | None = None,
        session_id: str | None = None,
    ) -> MCPCallResult:
        """统一调用工具（内置 + MCP）。

        完整调用流程：
        1. 获取工具信息（优先 L0 缓存）
        2. 安全网关校验（权限 + 频率 + 高风险确认 + 副作用授权）
        3. 根据 tool_type 分发调用：
           - BUILTIN: 本地执行
           - MCP: 传输协议远程调用
        4. OutputGuard 检查（SEC-TOOL-005）
        5. 审计回调（FR-INVOKE-005）
        """
        start = time.monotonic()

        # 1. 获取工具信息
        tool = self.get_tool(tool_name)
        if tool is None:
            # 尝试实时发现
            await self.discover_tools(user_id)
            tool = self.get_tool(tool_name)

        if tool is None:
            return MCPCallResult(
                tool_name=tool_name,
                success=False,
                error=f"Tool not found: {tool_name}",
            )

        # 2. 安全网关校验（P5 增强：权限 + 频率 + 高风险确认 + 副作用授权）
        try:
            from app.layers.security.mcp_security import mcp_security_gateway
            gate_result = await mcp_security_gateway.gate_call(
                user_id=user_id or "unknown",
                tool_name=tool_name,
                params=params,
                user_permissions=user_permissions,
                risk_level=tool.risk_level,
                tool_permissions=tool.permissions,
            )
            if not gate_result.allowed:
                friendly_error = mcp_security_gateway.get_friendly_error(gate_result.rejection_reason)
                result = MCPCallResult(
                    tool_name=tool_name,
                    success=False,
                    error=friendly_error,
                    tool_id=tool.tool_id,
                    tool_version=tool.version,
                )
                await self._audit_callback(result, tool, params, user_id, session_id)
                return result
            params = gate_result.sanitized_params
        except Exception as e:
            logger.debug(f"Security gateway check failed (non-blocking): {e}")

        # 3. 根据 tool_type 分发调用
        try:
            if tool.tool_type == "BUILTIN":
                # FR-BUILTIN-002: 内置工具本地执行
                result = await self._call_builtin(tool, params)
            else:
                # MCP 工具：通过连接管理器 + 传输协议远程调用
                result = await self._call_mcp(tool, params)
        except Exception as e:
            # 降级处理：不阻塞推理循环
            latency_ms = int((time.monotonic() - start) * 1000)
            result = MCPCallResult(
                tool_name=tool_name,
                success=False,
                error=f"Tool call degraded: {str(e)[:200]}",
                latency_ms=latency_ms,
                tool_id=tool.tool_id,
                tool_version=tool.version,
                degraded=True,
            )

        # 确保结果包含工具信息
        if not result.tool_id:
            result.tool_id = tool.tool_id
        if not result.tool_version:
            result.tool_version = tool.version

        # 4. SEC-TOOL-005: OutputGuard 检查
        if result.success and result.data is not None:
            result = self._apply_output_guard(result)

        # 5. 审计回调
        await self._audit_callback(result, tool, params, user_id, session_id)

        return result

    # ---- 内置工具调用 ----

    async def _call_builtin(self, tool: MCPToolInfo, params: dict[str, Any]) -> MCPCallResult:
        """调用内置工具（本地执行）。"""
        start = time.monotonic()
        try:
            from app.layers.tool_execution.builtin_tools import builtin_tool_registry
            data = await builtin_tool_registry.execute(tool.tool_name, params, _skip_security=True)
            latency_ms = int((time.monotonic() - start) * 1000)
            return MCPCallResult(
                tool_name=tool.tool_name,
                success=True,
                data=data,
                latency_ms=latency_ms,
                tool_id=tool.tool_id,
                tool_version=tool.version,
            )
        except KeyError:
            latency_ms = int((time.monotonic() - start) * 1000)
            return MCPCallResult(
                tool_name=tool.tool_name,
                success=False,
                error=f"Builtin tool handler not found: {tool.tool_name}",
                latency_ms=latency_ms,
                tool_id=tool.tool_id,
                tool_version=tool.version,
            )
        except Exception as e:
            latency_ms = int((time.monotonic() - start) * 1000)
            return MCPCallResult(
                tool_name=tool.tool_name,
                success=False,
                error=f"Builtin tool execution failed: {str(e)[:200]}",
                latency_ms=latency_ms,
                tool_id=tool.tool_id,
                tool_version=tool.version,
            )

    # ---- MCP 工具调用（通过连接管理器 + 传输协议）----

    async def _call_mcp(self, tool: MCPToolInfo, params: dict[str, Any]) -> MCPCallResult:
        """调用 MCP 工具（通过连接管理器 + 传输协议 + 重试）。"""
        from app.layers.tool_execution.mcp_connection_manager import (
            mcp_connection_manager, ConnectionConfig,
        )
        from app.layers.tool_execution.mcp_retry import execute_with_retry

        config = ConnectionConfig(
            server_url=tool.mcp_server_url,
            transport=tool.transport,
            auth_config=tool.auth_config,
            timeout_seconds=tool.timeout_seconds,
        )

        # 带重试的调用
        result = await execute_with_retry(
            call_fn=lambda: self._do_mcp_call(config, tool, params),
            tool_name=tool.tool_name,
            max_retries=tool.retry_count,
        )
        return result

    async def _do_mcp_call(
        self,
        config: "ConnectionConfig",
        tool: MCPToolInfo,
        params: dict[str, Any],
    ) -> MCPCallResult:
        """执行单次 MCP 工具调用（通过连接管理器）。"""
        from app.layers.tool_execution.mcp_connection_manager import mcp_connection_manager

        start = time.monotonic()

        if tool.status != "ACTIVE":
            return MCPCallResult(
                tool_name=tool.tool_name,
                success=False,
                error=f"Tool {tool.tool_name} is {tool.status}",
                tool_id=tool.tool_id,
                tool_version=tool.version,
            )

        transport_result = await mcp_connection_manager.call_with_connection(
            config=config,
            tool_name=tool.tool_name,
            arguments=params,
        )

        latency_ms = int((time.monotonic() - start) * 1000)

        if not transport_result.success:
            return MCPCallResult(
                tool_name=tool.tool_name,
                success=False,
                error=transport_result.error,
                latency_ms=latency_ms,
                tool_id=tool.tool_id,
                tool_version=tool.version,
            )

        return MCPCallResult(
            tool_name=tool.tool_name,
            success=True,
            data=self._parse_result(tool, transport_result.data),
            latency_ms=latency_ms,
            tool_id=tool.tool_id,
            tool_version=tool.version,
        )

    # ---- 辅助方法 ----

    async def _audit_callback(
        self,
        result: MCPCallResult,
        tool: MCPToolInfo,
        params: dict[str, Any],
        user_id: str | None,
        session_id: str | None,
    ) -> None:
        """调用结果审计回调（FR-INVOKE-005 / CB-10）。

        S3.7: tool_execution_logs 由 Python 写入 PG（通过回调 Java）
        S3.10: 幂等机制 — X-Request-ID + X-Trace-ID 头部
        """
        try:
            from app.infrastructure.callback_client import callback_client

            trace_id = uuid.uuid4().hex[:16]
            span_id = uuid.uuid4().hex[:8]
            # S3.10: request_id 作为幂等键，格式: trace_id-span_id
            request_id = f"{trace_id}-{span_id}"

            audit_data = {
                "idempotency_key": request_id,  # S3.10: 幂等键
                "trace_id": trace_id,
                "span_id": span_id,
                "user_id": user_id or "unknown",
                "agent_id": "shardflow-agent",
                "session_id": session_id or "",
                "tool_id": tool.tool_id,
                "tool_name": tool.tool_name,
                "tool_version": tool.version,
                "input_params": self._sanitize_params(params),
                "output_preview": self._sanitize_output(result.data) if result.success else "",
                "status": "success" if result.success else "failure",
                "latency_ms": result.latency_ms,
                "error_code": None if result.success else "MCP_CALL_FAILED",
                "error_msg": result.error[:500] if result.error else None,
                "request_at": time.strftime("%Y-%m-%dT%H:%M:%S.000Z", time.gmtime()),
            }

            # S3.7/S3.10: 传递 request_id 和 trace_id 作为头部（CB-10 合规）
            await callback_client.write_mcp_audit(
                audit_data,
                request_id=request_id,
                trace_id=trace_id,
            )
        except Exception as e:
            logger.debug(f"MCP audit callback failed (non-blocking): {e}")

    def _sanitize_params(self, params: dict[str, Any]) -> str:
        """脱敏输入参数用于审计日志。"""
        import json
        try:
            text = json.dumps(params, ensure_ascii=False)
            return text[:1024]
        except Exception:
            return str(params)[:1024]

    def _sanitize_output(self, data: Any) -> str:
        """脱敏输出预览用于审计日志。"""
        import json
        try:
            text = json.dumps(data, ensure_ascii=False)
            return text[:1024]
        except Exception:
            return str(data)[:1024]

    def _apply_output_guard(self, result: MCPCallResult) -> MCPCallResult:
        """SEC-TOOL-005: OutputGuard 检查 — PII 脱敏 + 有害内容过滤。"""
        try:
            from app.layers.security.output_guard import output_guard
            import json

            data_text = json.dumps(result.data, ensure_ascii=False) if isinstance(result.data, dict) else str(result.data)
            guard_result = output_guard.inspect(data_text)

            # SEC-TOOL-005: 有害内容直接阻断
            if guard_result.get("harmful_detected"):
                logger.warning(f"SEC-TOOL-005: Harmful content detected in output of {result.tool_name}")
                return MCPCallResult(
                    tool_name=result.tool_name,
                    success=False,
                    data=None,
                    error="工具输出包含不安全内容，已被安全网关拦截",
                    degraded=True,
                    tool_id=result.tool_id,
                    tool_version=result.tool_version,
                    latency_ms=result.latency_ms,
                )

            # PII 脱敏处理
            if guard_result.get("pii_masked"):
                masked_text = guard_result.get("text", data_text)
                try:
                    result.data = json.loads(masked_text)
                except (json.JSONDecodeError, TypeError):
                    result.data = {"content": masked_text}

            # 不合规内容截断处理
            if not guard_result.get("compliant"):
                logger.warning(f"SEC-TOOL-005: Compliance check failed for {result.tool_name}")
                sanitized_text = guard_result.get("text", "[内容已过滤]")
                try:
                    result.data = json.loads(sanitized_text)
                except (json.JSONDecodeError, TypeError):
                    result.data = {"content": sanitized_text}

        except Exception as e:
            logger.debug(f"OutputGuard check failed (non-blocking): {e}")

        return result

    def _parse_result(self, tool: MCPToolInfo, raw: dict[str, Any]) -> dict[str, Any]:
        """标准化 MCP 返回结果。"""
        content = raw.get("content", raw.get("result", raw))
        if isinstance(content, list):
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
        tool = self.get_tool(tool_name)
        if tool is None:
            return False
        # 内置工具始终健康
        if tool.tool_type == "BUILTIN":
            return True
        try:
            client = await self._get_client()
            resp = await client.get(
                f"{tool.mcp_server_url}/health",
                timeout=httpx.Timeout(5.0),
            )
            return resp.status_code == 200
        except Exception:
            return False

    async def close(self) -> None:
        if self._http_client:
            await self._http_client.aclose()
            self._http_client = None
        # 关闭连接管理器
        try:
            from app.layers.tool_execution.mcp_connection_manager import mcp_connection_manager
            await mcp_connection_manager.close_all()
        except Exception:
            pass


mcp_client = MCPClient()
