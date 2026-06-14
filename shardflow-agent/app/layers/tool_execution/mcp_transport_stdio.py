"""L5 Tool Execution: MCP stdio 传输协议实现。

P6 阶段实现 (FR-CONN-002):
- 支持 stdio 子进程连接建立和通信
- MCP 标准协议: 启动子进程，通过 stdin/stdout JSON-RPC 通信
- 支持本地 MCP Server 进程管理
"""
import asyncio
import json
import logging
import time
import uuid
from typing import Any

from app.layers.tool_execution.mcp_transport_base import BaseTransport, TransportResult

logger = logging.getLogger(__name__)


class StdioTransport(BaseTransport):
    """stdio 传输协议实现。

    MCP stdio 协议流程:
    1. 启动子进程（command + args）
    2. 通过 stdin 发送 JSON-RPC 请求
    3. 从 stdout 读取 JSON-RPC 响应
    4. 子进程生命周期管理
    """

    def __init__(self) -> None:
        self._processes: dict[str, asyncio.subprocess.Process] = {}

    def protocol_name(self) -> str:
        return "stdio"

    async def call_tool(
        self,
        server_url: str,
        tool_name: str,
        arguments: dict[str, Any],
        timeout_seconds: int = 30,
        auth_config: dict[str, Any] | None = None,
    ) -> TransportResult:
        """通过 stdio 协议调用 MCP 工具。

        server_url 格式: command arg1 arg2 ...（空格分隔的命令行）
        例如: "python mcp_server.py --port 8080"
        """
        start = time.monotonic()

        try:
            # 获取或创建子进程
            process = await self._get_or_create_process(server_url)

            # 构建 JSON-RPC 请求（使用唯一 ID 区分并发调用）
            request = {
                "jsonrpc": "2.0",
                "id": uuid.uuid4().hex[:8],
                "method": "tools/call",
                "params": {
                    "name": tool_name,
                    "arguments": arguments,
                },
            }

            # 通过 stdin 发送请求
            request_str = json.dumps(request) + "\n"
            process.stdin.write(request_str.encode("utf-8"))
            await process.stdin.drain()

            # 从 stdout 读取响应（带超时）
            try:
                response_line = await asyncio.wait_for(
                    process.stdout.readline(), timeout=float(timeout_seconds)
                )
            except asyncio.TimeoutError:
                latency_ms = int((time.monotonic() - start) * 1000)
                return TransportResult(
                    success=False,
                    error=f"stdio call timeout after {latency_ms}ms (limit={timeout_seconds}s)",
                    latency_ms=latency_ms,
                )

            if not response_line:
                latency_ms = int((time.monotonic() - start) * 1000)
                return TransportResult(
                    success=False,
                    error="stdio process closed stdout unexpectedly",
                    latency_ms=latency_ms,
                )

            # 解析 JSON-RPC 响应
            response = json.loads(response_line.decode("utf-8").strip())
            latency_ms = int((time.monotonic() - start) * 1000)

            # 检查 JSON-RPC 错误
            if "error" in response:
                error = response["error"]
                return TransportResult(
                    success=False,
                    error=f"JSON-RPC error: {error.get('message', str(error))[:200]}",
                    latency_ms=latency_ms,
                )

            # 提取结果
            result = response.get("result", {})
            return TransportResult(
                success=True,
                data=self._parse_result(result),
                latency_ms=latency_ms,
            )

        except json.JSONDecodeError as e:
            latency_ms = int((time.monotonic() - start) * 1000)
            return TransportResult(
                success=False,
                error=f"stdio response parse error: {str(e)[:200]}",
                latency_ms=latency_ms,
            )
        except FileNotFoundError as e:
            latency_ms = int((time.monotonic() - start) * 1000)
            return TransportResult(
                success=False,
                error=f"stdio command not found: {str(e)[:200]}",
                latency_ms=latency_ms,
            )
        except Exception as e:
            latency_ms = int((time.monotonic() - start) * 1000)
            return TransportResult(
                success=False,
                error=f"stdio call failed: {str(e)[:200]}",
                latency_ms=latency_ms,
            )

    async def _get_or_create_process(
        self, server_url: str
    ) -> asyncio.subprocess.Process:
        """获取或创建 stdio 子进程。

        对同一 server_url 复用子进程，避免重复启动。
        """
        if server_url in self._processes:
            process = self._processes[server_url]
            if process.returncode is None:
                return process
            # 进程已退出，移除旧引用
            del self._processes[server_url]

        # 解析命令行
        parts = server_url.split()
        if not parts:
            raise ValueError(f"Invalid stdio command: {server_url}")

        command = parts[0]
        args = parts[1:]

        process = await asyncio.create_subprocess_exec(
            command,
            *args,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        self._processes[server_url] = process
        logger.info(f"Started stdio MCP process: {server_url} (pid={process.pid})")
        return process

    def _parse_result(self, result: dict[str, Any]) -> dict[str, Any]:
        """解析 MCP 工具调用结果。"""
        content = result.get("content", result)
        if isinstance(content, list):
            # MCP 标准格式: content: [{type: "text", text: "..."}]
            text_parts = []
            for item in content:
                if isinstance(item, dict) and item.get("type") == "text":
                    text_parts.append(str(item.get("text", "")))
            return {
                "content": "\n".join(text_parts) if text_parts else str(content),
                "raw": result,
            }
        return {
            "content": str(content),
            "raw": result,
        }

    async def close(self) -> None:
        """关闭所有 stdio 子进程。"""
        for url, process in self._processes.items():
            if process.returncode is None:
                try:
                    process.terminate()
                    await asyncio.wait_for(process.wait(), timeout=5.0)
                    logger.info(f"Terminated stdio process: {url}")
                except asyncio.TimeoutError:
                    process.kill()
                    logger.warning(f"Killed stdio process: {url}")
                except Exception as e:
                    logger.warning(f"Error closing stdio process {url}: {e}")
        self._processes.clear()
