"""L5 Tool Execution: MCP 连接管理器。

P6 阶段实现 (FR-CONN-001, FR-CONN-003, FR-CONN-004):
- 连接信息配置管理（URL/协议/认证）
- 连接失败错误日志（地址+错误类型+时间戳）
- 连接信息变更自动重连（断旧建新）
- 传输协议实例管理（HTTP-SSE / stdio）
"""
import logging
import time
from dataclasses import dataclass, field
from typing import Any

from app.layers.tool_execution.mcp_transport_base import BaseTransport, TransportResult
from app.layers.tool_execution.mcp_transport_http_sse import HttpSseTransport
from app.layers.tool_execution.mcp_transport_stdio import StdioTransport

logger = logging.getLogger(__name__)


@dataclass
class ConnectionErrorLog:
    """连接错误日志条目 (FR-CONN-003)。"""
    server_url: str
    error_type: str
    error_message: str
    timestamp: float = field(default_factory=time.time)


@dataclass
class ConnectionConfig:
    """MCP Server 连接配置 (FR-CONN-001)。"""
    server_url: str
    transport: str = "http-sse"  # http-sse / stdio / builtin
    auth_config: dict[str, Any] | None = None
    timeout_seconds: int = 30


class McpConnectionManager:
    """MCP Server 连接管理器。

    职责:
    - 管理传输协议实例（按 server_url 缓存）
    - 记录连接失败错误日志
    - 连接信息变更时自动重连（断旧建新）
    """

    def __init__(self) -> None:
        self._transports: dict[str, BaseTransport] = {}
        self._configs: dict[str, ConnectionConfig] = {}
        self._error_logs: list[ConnectionErrorLog] = []
        self._max_error_logs = 1000

    def get_transport(self, config: ConnectionConfig) -> BaseTransport:
        """获取传输协议实例（按 server_url 缓存）。

        如果配置变更（transport 类型变化），自动断旧建新 (FR-CONN-004)。
        """
        url = config.server_url
        transport_type = config.transport

        # 检查是否需要重建连接
        existing = self._transports.get(url)
        if existing is not None:
            # 传输类型未变，复用现有连接
            if existing.protocol_name() == transport_type:
                # 更新配置
                self._configs[url] = config
                return existing
            # 传输类型变更，断旧建新 (FR-CONN-004)
            logger.info(f"Transport type changed for {url}: "
                       f"{existing.protocol_name()} -> {transport_type}, reconnecting")
            self._disconnect(url)

        # 创建新的传输协议实例
        transport = self._create_transport(transport_type)
        self._transports[url] = transport
        self._configs[url] = config
        return transport

    async def call_with_connection(
        self,
        config: ConnectionConfig,
        tool_name: str,
        arguments: dict[str, Any],
    ) -> TransportResult:
        """通过连接管理器调用 MCP 工具。

        自动处理传输协议选择、错误日志记录。
        """
        transport = self.get_transport(config)

        try:
            result = await transport.call_tool(
                server_url=config.server_url,
                tool_name=tool_name,
                arguments=arguments,
                timeout_seconds=config.timeout_seconds,
                auth_config=config.auth_config,
            )

            # 记录失败日志 (FR-CONN-003)
            if not result.success:
                self._log_connection_error(
                    server_url=config.server_url,
                    error_type="call_failed",
                    error_message=result.error,
                )

            return result

        except Exception as e:
            # 记录连接异常日志 (FR-CONN-003)
            self._log_connection_error(
                server_url=config.server_url,
                error_type="connection_exception",
                error_message=str(e)[:200],
            )
            return TransportResult(
                success=False,
                error=f"Connection error: {str(e)[:200]}",
            )

    def _create_transport(self, transport_type: str) -> BaseTransport:
        """创建传输协议实例。"""
        if transport_type == "http-sse":
            return HttpSseTransport()
        elif transport_type == "stdio":
            return StdioTransport()
        else:
            logger.warning(f"Unknown transport type: {transport_type}, falling back to http-sse")
            return HttpSseTransport()

    async def _disconnect(self, server_url: str) -> None:
        """断开指定 server_url 的连接。"""
        transport = self._transports.pop(server_url, None)
        if transport is not None:
            try:
                await transport.close()
                logger.info(f"Disconnected transport for: {server_url}")
            except Exception as e:
                logger.warning(f"Error disconnecting transport for {server_url}: {e}")

    def _log_connection_error(
        self,
        server_url: str,
        error_type: str,
        error_message: str,
    ) -> None:
        """记录连接错误日志 (FR-CONN-003)。"""
        log_entry = ConnectionErrorLog(
            server_url=server_url,
            error_type=error_type,
            error_message=error_message,
        )
        self._error_logs.append(log_entry)

        # 限制日志数量
        if len(self._error_logs) > self._max_error_logs:
            self._error_logs = self._error_logs[-self._max_error_logs:]

        logger.warning(f"MCP connection error: url={server_url}, "
                      f"type={error_type}, msg={error_message[:100]}")

    def get_error_logs(
        self,
        server_url: str | None = None,
        limit: int = 50,
    ) -> list[ConnectionErrorLog]:
        """获取连接错误日志。

        Args:
            server_url: 按地址筛选（None 表示全部）
            limit: 返回条数上限
        """
        logs = self._error_logs
        if server_url:
            logs = [l for l in logs if l.server_url == server_url]
        return logs[-limit:]

    async def reconnect(self, server_url: str) -> bool:
        """手动重连指定 server_url (FR-CONN-004)。

        断开旧连接，下次调用时自动创建新连接。
        """
        await self._disconnect(server_url)
        self._configs.pop(server_url, None)
        logger.info(f"Reconnected: {server_url}")
        return True

    async def close_all(self) -> None:
        """关闭所有连接。"""
        for url in list(self._transports.keys()):
            await self._disconnect(url)
        self._configs.clear()
        logger.info("All MCP connections closed")


# 全局单例
mcp_connection_manager = McpConnectionManager()
