"""L5 Tool Execution: Smithery 平台 MCP 适配器实现。

P3 阶段实现:
- 支持 Smithery 云托管 MCP Server 调用
- Bearer Token 认证 (API Key)
- MCP 标准响应解析
- 异常处理: 超时、认证失败、Server Not Found
"""
import json
import logging
import time
from typing import Any

import httpx

from app.layers.tool_execution.mcp_cloud_base import CloudProviderAdapter
from app.layers.tool_execution.mcp_transport_base import TransportResult

logger = logging.getLogger(__name__)


class SmitheryAdapter(CloudProviderAdapter):
    """Smithery 平台适配器。

    Smithery 提供托管的 MCP Server 端点，通过 API Key 认证。
    用户只需在 smithery.ai 注册获取 API Key，无需管理服务器。

    API 调用格式:
        POST https://api.smithery.ai/v1/servers/{server_key}/tools/{tool_name}/call
        Headers: Authorization: Bearer {api_key}
        Body: {"arguments": {...}}
    """

    BASE_URL = "https://api.smithery.ai"

    def protocol_name(self) -> str:
        return "cloud-smithery"

    def provider_name(self) -> str:
        return "smithery"

    async def call_tool(
        self,
        tool_name: str,
        arguments: dict[str, Any],
        timeout_seconds: int = 30,
        auth_config: dict[str, Any] | None = None,
    ) -> TransportResult:
        """调用 Smithery 托管的 MCP 工具。"""
        start = time.monotonic()

        # 提取认证配置
        if not auth_config:
            return TransportResult(
                success=False,
                error="Smithery adapter requires auth_config with api_key and server_key",
            )

        api_key = auth_config.get("api_key", "")
        server_key = auth_config.get("server_key", "")

        if not api_key or not server_key:
            return TransportResult(
                success=False,
                error="Missing required auth_config fields: api_key or server_key",
            )

        try:
            async with httpx.AsyncClient(
                timeout=httpx.Timeout(float(timeout_seconds))
            ) as client:
                # 构建 API URL
                url = f"{self.BASE_URL}/v1/servers/{server_key}/tools/{tool_name}/call"

                # 发送调用请求
                resp = await client.post(
                    url,
                    json={"arguments": arguments},
                    headers={
                        "Authorization": f"Bearer {api_key}",
                        "Content-Type": "application/json",
                    },
                )

                latency_ms = int((time.monotonic() - start) * 1000)

                if resp.status_code == 401:
                    return TransportResult(
                        success=False,
                        error="Smithery authentication failed: invalid API key",
                        status_code=401,
                        latency_ms=latency_ms,
                    )

                if resp.status_code == 404:
                    return TransportResult(
                        success=False,
                        error=f"Smithery server or tool not found: server_key={server_key}, tool={tool_name}",
                        status_code=404,
                        latency_ms=latency_ms,
                    )

                if resp.status_code >= 400:
                    error_text = resp.text[:200]
                    return TransportResult(
                        success=False,
                        error=f"Smithery API error {resp.status_code}: {error_text}",
                        status_code=resp.status_code,
                        latency_ms=latency_ms,
                    )

                # 解析 MCP 标准响应
                response_data = resp.json()
                extracted_data = self._extract_mcp_content(response_data)

                return TransportResult(
                    success=True,
                    data=extracted_data,
                    latency_ms=latency_ms,
                )

        except httpx.TimeoutException:
            latency_ms = int((time.monotonic() - start) * 1000)
            return TransportResult(
                success=False,
                error=f"Smithery call timeout after {latency_ms}ms (limit={timeout_seconds}s)",
                latency_ms=latency_ms,
            )

        except httpx.ConnectError as e:
            latency_ms = int((time.monotonic() - start) * 1000)
            return TransportResult(
                success=False,
                error=f"Smithery connection failed: {str(e)[:200]}",
                latency_ms=latency_ms,
            )

        except json.JSONDecodeError as e:
            latency_ms = int((time.monotonic() - start) * 1000)
            return TransportResult(
                success=False,
                error=f"Smithery response parse error: {str(e)[:200]}",
                latency_ms=latency_ms,
            )

        except Exception as e:
            latency_ms = int((time.monotonic() - start) * 1000)
            logger.error(f"Smithery adapter unexpected error: {e}", exc_info=True)
            return TransportResult(
                success=False,
                error=f"Smithery call failed: {str(e)[:200]}",
                latency_ms=latency_ms,
            )

    async def validate_auth(self, auth_config: dict[str, Any]) -> bool:
        """验证 Smithery 认证配置是否有效。

        验证逻辑:
        1. 检查 api_key 和 server_key 是否存在
        2. 可选: 调用 Smithery API 验证 key 有效性（P4 增强）
        """
        api_key = auth_config.get("api_key", "")
        server_key = auth_config.get("server_key", "")

        if not api_key or not server_key:
            logger.warning("Smithery auth validation failed: missing api_key or server_key")
            return False

        # P3: 仅检查字段存在性，P4 可增加实际 API 验证
        return True