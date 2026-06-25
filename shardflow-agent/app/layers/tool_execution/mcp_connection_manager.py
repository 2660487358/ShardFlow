"""L5 Tool Execution: MCP 连接管理器。

P6 阶段实现 (FR-CONN-001, FR-CONN-003, FR-CONN-004):
- 连接信息配置管理（URL/协议/认证）
- 连接失败错误日志（地址+错误类型+时间戳）
- 连接信息变更自动重连（断旧建新）
- 传输协议实例管理（HTTP-SSE / stdio）
- SSE autoStart 流程（P6 新增）：检查 url 可达性→启动子进程→轮询端口→超时处理
"""
import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Any

import httpx

from app.layers.tool_execution.mcp_transport_base import BaseTransport, TransportResult
from app.layers.tool_execution.mcp_transport_cloud import CloudTransport
from app.layers.tool_execution.mcp_transport_http_sse import HttpSseTransport
from app.layers.tool_execution.mcp_transport_stdio import StdioTransport

logger = logging.getLogger(__name__)


async def async_empty():
    """异步空生成器，用于优雅处理 None 流。"""
    for _ in range(0):
        yield b""


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
    transport: str = "http-sse"  # http-sse / stdio / builtin / cloud
    auth_config: dict[str, Any] | None = None
    timeout_seconds: int = 30
    # P6 autoStart 新增字段
    auto_start: bool = False
    start_command: str | None = None  # 如 "npx"
    start_args: list[str] | None = None  # 如 ["-y", "@modelcontextprotocol/server-github"]


class McpConnectionManager:
    """MCP Server 连接管理器。

    职责:
    - 管理传输协议实例（按 server_url 缓存）
    - 记录连接失败错误日志
    - 连接信息变更时自动重连（断旧建新）
    - P6: SSE autoStart 流程（启动本地 MCP Server 子进程）
    """

    def __init__(self) -> None:
        self._transports: dict[str, BaseTransport] = {}
        self._configs: dict[str, ConnectionConfig] = {}
        self._error_logs: list[ConnectionErrorLog] = []
        self._max_error_logs = 1000
        self._subprocesses: dict[str, asyncio.subprocess.Process] = {}  # P6: 子进程管理

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
        # P6: 如果是 SSE 模式且设置了 autoStart，先确保服务已启动
        if config.transport == "http-sse" and config.auto_start:
            started = await self.auto_start_server(config)
            if not started:
                return TransportResult(
                    success=False,
                    error=f"AutoStart failed for {config.server_url}: "
                          f"server not reachable after startup attempt",
                )

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
        elif transport_type == "cloud":
            return CloudTransport()
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

    async def auto_start_server(self, config: ConnectionConfig) -> bool:
        """SSE autoStart 流程 (P6)。

        1. 检查 config.server_url 是否可达（HEAD 请求）
        2. 不可达 → 从模板获取启动命令（command + args）
        3. 调用 asyncio.create_subprocess_exec 启动子进程
        4. 轮询等待端口就绪（最多 30s，间隔 1s）
        5. 就绪 → 返回 True；超时 → 返回 False

        Args:
            config: 连接配置（需含 start_command / start_args）

        Returns:
            True 表示服务已就绪，False 表示启动失败
        """
        server_url = config.server_url

        # Step 1: 检查是否已可达
        if await self._check_url_reachable(server_url, timeout=3):
            logger.info(f"Server {server_url} already reachable, no autoStart needed")
            return True

        # 已在运行中（之前启动过的子进程）
        if server_url in self._subprocesses:
            proc = self._subprocesses[server_url]
            if proc.returncode is None:
                # 进程还在运行，但端口未就绪 → 继续等待
                logger.info(f"Subprocess for {server_url} already running, waiting for port")
                return await self._poll_port_ready(server_url, timeout_seconds=30)
            else:
                # 进程已退出，清理后重新启动
                logger.warning(f"Subprocess for {server_url} exited with code {proc.returncode}, restarting")
                del self._subprocesses[server_url]

        # Step 2: 检查启动命令
        if not config.start_command:
            self._log_connection_error(
                server_url=server_url,
                error_type="auto_start_no_command",
                error_message="autoStart enabled but no start_command provided",
            )
            logger.warning(f"autoStart: no start_command for {server_url}")
            return False

        # Step 3: 启动子进程
        try:
            command = [config.start_command]
            if config.start_args:
                command.extend(config.start_args)

            logger.info(f"autoStart: launching subprocess for {server_url}: {' '.join(command)}")

            proc = await asyncio.create_subprocess_exec(
                *command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            self._subprocesses[server_url] = proc

            # 后台读取 stdout/stderr 防止缓冲区阻塞
            asyncio.create_task(self._pipe_subprocess_output(server_url, proc))

        except FileNotFoundError:
            self._log_connection_error(
                server_url=server_url,
                error_type="auto_start_command_not_found",
                error_message=f"Command not found: {config.start_command}",
            )
            logger.error(f"autoStart: command not found '{config.start_command}' for {server_url}")
            logger.info(f"autoStart: Please install the required runtime: {config.start_command}")
            return False
        except Exception as e:
            self._log_connection_error(
                server_url=server_url,
                error_type="auto_start_launch_error",
                error_message=str(e)[:200],
            )
            logger.error(f"autoStart: failed to launch subprocess for {server_url}: {e}")
            return False

        # Step 4: 轮询等待端口就绪
        return await self._poll_port_ready(server_url, timeout_seconds=30)

    async def _check_url_reachable(self, url: str, timeout: int = 3) -> bool:
        """检查 URL 是否可达（HEAD 请求）。"""
        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(timeout)) as client:
                resp = await client.head(url, follow_redirects=True)
                return resp.status_code < 500
        except (httpx.TimeoutException, httpx.ConnectError, httpx.RequestError):
            return False

    async def _poll_port_ready(self, server_url: str, timeout_seconds: int = 30) -> bool:
        """轮询等待端口就绪。

        每 1s 检查一次 URL 可达性，最多等待 timeout_seconds 秒。
        """
        deadline = time.time() + timeout_seconds
        attempt = 0

        while time.time() < deadline:
            attempt += 1
            if await self._check_url_reachable(server_url, timeout=2):
                logger.info(f"autoStart: server {server_url} ready after ~{attempt}s")
                return True
            await asyncio.sleep(1)

        # 超时 — 记录详细诊断信息
        proc = self._subprocesses.get(server_url)
        diag_parts = [f"Server {server_url} not reachable after {timeout_seconds}s"]

        if proc and proc.returncode is not None:
            diag_parts.append(f"process exited with code {proc.returncode}")

        diag_parts.append("Troubleshooting tips:")
        diag_parts.append("  1. Check if the required runtime (node/npx/python) is installed")
        diag_parts.append("  2. Verify the start command and args are correct")
        diag_parts.append(f"  3. Ensure port in {server_url} is not blocked by firewall")

        error_msg = "\n".join(diag_parts)
        self._log_connection_error(
            server_url=server_url,
            error_type="auto_start_timeout",
            error_message=error_msg[:200],
        )
        logger.error(f"autoStart: {error_msg}")
        return False

    async def _pipe_subprocess_output(
        self,
        server_url: str,
        proc: asyncio.subprocess.Process,
    ) -> None:
        """后台读取子进程 stdout/stderr，防止缓冲区阻塞。"""
        try:
            async for line in proc.stderr if proc.stderr else async_empty():
                text = line.decode("utf-8", errors="replace").rstrip()
                if text:
                    logger.debug(f"[{server_url} stderr] {text}")
        except Exception:
            pass

    async def close_all(self) -> None:
        """关闭所有连接和子进程。"""
        # 关闭所有传输连接
        for url in list(self._transports.keys()):
            await self._disconnect(url)
        self._configs.clear()

        # 关闭所有 autoStart 子进程 (P6)
        for url, proc in list(self._subprocesses.items()):
            if proc.returncode is None:
                proc.terminate()
                try:
                    await asyncio.wait_for(proc.wait(), timeout=5)
                except asyncio.TimeoutError:
                    proc.kill()
                logger.info(f"autoStart: terminated subprocess for {url}")
        self._subprocesses.clear()

        logger.info("All MCP connections and subprocesses closed")


# 全局单例
mcp_connection_manager = McpConnectionManager()
