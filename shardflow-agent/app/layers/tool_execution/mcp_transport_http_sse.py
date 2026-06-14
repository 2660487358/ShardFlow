"""L5 Tool Execution: MCP HTTP-SSE 传输协议实现。

P6 阶段实现 (FR-CONN-002):
- 支持 HTTP-SSE 连接建立和通信
- MCP 标准协议: POST /tools/call 发送请求
- 支持 SSE 流式响应解析
- 认证头注入
"""
import json
import logging
import time
from typing import Any

import httpx

from app.layers.tool_execution.mcp_transport_base import BaseTransport, TransportResult

logger = logging.getLogger(__name__)


class HttpSseTransport(BaseTransport):
    """HTTP-SSE 传输协议实现。

    MCP 标准协议流程:
    1. POST {server_url}/tools/call 发送工具调用请求
    2. 响应为 SSE 流或标准 JSON
    3. 解析响应内容
    """

    def __init__(self) -> None:
        self._client: httpx.AsyncClient | None = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=httpx.Timeout(30.0))
        return self._client

    def protocol_name(self) -> str:
        return "http-sse"

    async def call_tool(
        self,
        server_url: str,
        tool_name: str,
        arguments: dict[str, Any],
        timeout_seconds: int = 30,
        auth_config: dict[str, Any] | None = None,
    ) -> TransportResult:
        """通过 HTTP-SSE 协议调用 MCP 工具。"""
        start = time.monotonic()

        try:
            client = await self._get_client()

            # 构建请求头
            headers: dict[str, str] = {"Content-Type": "application/json"}
            # Basic auth 通过 httpx auth 参数传入，不通过 headers
            basic_auth = None
            if auth_config:
                auth_type = auth_config.get("type", "").lower()
                if auth_type == "basic":
                    basic_auth = self._build_basic_auth(auth_config)
                else:
                    headers.update(self._build_auth_headers(auth_config))

            # 发送 MCP 标准调用请求
            resp = await client.post(
                f"{server_url}/tools/call",
                json={"name": tool_name, "arguments": arguments},
                headers=headers,
                auth=basic_auth,
                timeout=httpx.Timeout(float(timeout_seconds)),
            )

            latency_ms = int((time.monotonic() - start) * 1000)

            if resp.status_code >= 400:
                return TransportResult(
                    success=False,
                    error=f"MCP server returned {resp.status_code}: {resp.text[:200]}",
                    status_code=resp.status_code,
                    latency_ms=latency_ms,
                )

            # 解析响应（支持标准 JSON 和 SSE 格式）
            data = self._parse_response(resp)
            return TransportResult(
                success=True,
                data=data,
                latency_ms=latency_ms,
            )

        except httpx.TimeoutException:
            latency_ms = int((time.monotonic() - start) * 1000)
            return TransportResult(
                success=False,
                error=f"HTTP-SSE call timeout after {latency_ms}ms (limit={timeout_seconds}s)",
                latency_ms=latency_ms,
            )
        except httpx.ConnectError as e:
            latency_ms = int((time.monotonic() - start) * 1000)
            return TransportResult(
                success=False,
                error=f"HTTP-SSE connection failed: {str(e)[:200]}",
                latency_ms=latency_ms,
            )
        except Exception as e:
            latency_ms = int((time.monotonic() - start) * 1000)
            return TransportResult(
                success=False,
                error=f"HTTP-SSE call failed: {str(e)[:200]}",
                latency_ms=latency_ms,
            )

    def _build_auth_headers(self, auth_config: dict[str, Any]) -> dict[str, str]:
        """根据认证配置构建请求头。"""
        headers: dict[str, str] = {}
        auth_type = auth_config.get("type", "").lower()

        if auth_type == "bearer":
            token = auth_config.get("token", "")
            if token:
                headers["Authorization"] = f"Bearer {token}"
        elif auth_type == "api_key":
            key_name = auth_config.get("keyName", "X-API-Key")
            key_value = auth_config.get("keyValue", "")
            if key_value:
                headers[key_name] = key_value
        elif auth_type == "basic":
            # Basic auth 通过 httpx auth 参数传入，此处不构建 header
            pass

        return headers

    def _build_basic_auth(self, auth_config: dict[str, Any]) -> httpx.BasicAuth | None:
        """根据认证配置构建 Basic Auth 对象。"""
        username = auth_config.get("username", "")
        password = auth_config.get("password", "")
        if username:
            return httpx.BasicAuth(username, password)
        return None

    def _parse_response(self, resp: httpx.Response) -> dict[str, Any]:
        """解析 MCP 响应（支持标准 JSON 和 SSE 格式）。"""
        content_type = resp.headers.get("content-type", "")

        if "text/event-stream" in content_type:
            # SSE 流式响应：提取 data 行中的 JSON
            return self._parse_sse_response(resp.text)
        else:
            # 标准 JSON 响应
            return resp.json()

    def _parse_sse_response(self, sse_text: str) -> dict[str, Any]:
        """解析 SSE 流式响应文本。"""
        content_parts: list[str] = []

        for line in sse_text.split("\n"):
            if line.startswith("data: "):
                data_str = line[6:].strip()
                if data_str:
                    try:
                        data = json.loads(data_str)
                        # MCP SSE 格式: content 字段
                        if isinstance(data, dict):
                            content = data.get("content", data.get("result", ""))
                            if isinstance(content, list):
                                for item in content:
                                    if isinstance(item, dict) and item.get("type") == "text":
                                        content_parts.append(str(item.get("text", "")))
                            elif isinstance(content, str):
                                content_parts.append(content)
                    except json.JSONDecodeError:
                        content_parts.append(data_str)

        return {
            "content": "\n".join(content_parts) if content_parts else sse_text,
            "raw_sse": True,
        }

    async def close(self) -> None:
        if self._client:
            await self._client.aclose()
            self._client = None
