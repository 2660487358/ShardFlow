"""L5 Tool Execution: Google Cloud Managed MCP 适配器实现。

P3 阶段实现:
- 支持 Google Cloud Managed MCP 服务调用
- GCP ADC (Application Default Credentials) 自动认证
- Streamable HTTP 协议
- IAM 错误码映射 (403 → 权限不足提示)
"""
import json
import logging
import time
from typing import Any

import httpx

from app.layers.tool_execution.mcp_cloud_base import CloudProviderAdapter
from app.layers.tool_execution.mcp_transport_base import TransportResult

logger = logging.getLogger(__name__)


class GoogleManagedAdapter(CloudProviderAdapter):
    """Google Cloud Managed MCP 适配器。

    使用 GCP IAM 认证，无需管理密钥——
    通过 GCP Service Account 或用户凭证直接调用 Google 托管的 MCP 端点。

    API 调用格式:
        POST https://{server_id}/v1/mcp/tools/{tool_name}/call
        Headers: Authorization: Bearer {gcp_token}
        Body: {"arguments": {...}}
    """

    def protocol_name(self) -> str:
        return "cloud-google-managed"

    def provider_name(self) -> str:
        return "google-managed"

    async def call_tool(
        self,
        tool_name: str,
        arguments: dict[str, Any],
        timeout_seconds: int = 30,
        auth_config: dict[str, Any] | None = None,
    ) -> TransportResult:
        """调用 Google Managed MCP 工具。"""
        start = time.monotonic()

        # 提取认证配置
        if not auth_config:
            return TransportResult(
                success=False,
                error="Google Managed adapter requires auth_config with server_id",
            )

        server_id = auth_config.get("server_id", "")

        if not server_id:
            return TransportResult(
                success=False,
                error="Missing required auth_config field: server_id",
            )

        try:
            # 获取 GCP ADC Token
            gcp_token = await self._get_gcp_adc_token()
            if not gcp_token:
                return TransportResult(
                    success=False,
                    error="Failed to obtain GCP ADC token. Check credentials configuration.",
                )

            async with httpx.AsyncClient(
                timeout=httpx.Timeout(float(timeout_seconds))
            ) as client:
                # 构建 Google Managed MCP URL
                endpoint = f"https://{server_id}/v1/mcp"
                url = f"{endpoint}/tools/{tool_name}/call"

                # 发送调用请求
                resp = await client.post(
                    url,
                    json={"arguments": arguments},
                    headers={
                        "Authorization": f"Bearer {gcp_token}",
                        "Content-Type": "application/json",
                    },
                )

                latency_ms = int((time.monotonic() - start) * 1000)

                # IAM 错误码映射
                if resp.status_code == 403:
                    error_detail = self._parse_iam_error(resp)
                    return TransportResult(
                        success=False,
                        error=f"Google IAM permission denied: {error_detail}",
                        status_code=403,
                        latency_ms=latency_ms,
                    )

                if resp.status_code == 401:
                    return TransportResult(
                        success=False,
                        error="Google authentication failed: invalid or expired token",
                        status_code=401,
                        latency_ms=latency_ms,
                    )

                if resp.status_code == 404:
                    return TransportResult(
                        success=False,
                        error=f"Google Managed MCP server or tool not found: server_id={server_id}, tool={tool_name}",
                        status_code=404,
                        latency_ms=latency_ms,
                    )

                if resp.status_code >= 400:
                    error_text = resp.text[:200]
                    return TransportResult(
                        success=False,
                        error=f"Google Managed MCP error {resp.status_code}: {error_text}",
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
                error=f"Google Managed MCP call timeout after {latency_ms}ms (limit={timeout_seconds}s)",
                latency_ms=latency_ms,
            )

        except httpx.ConnectError as e:
            latency_ms = int((time.monotonic() - start) * 1000)
            return TransportResult(
                success=False,
                error=f"Google Managed MCP connection failed: {str(e)[:200]}",
                latency_ms=latency_ms,
            )

        except json.JSONDecodeError as e:
            latency_ms = int((time.monotonic() - start) * 1000)
            return TransportResult(
                success=False,
                error=f"Google Managed MCP response parse error: {str(e)[:200]}",
                latency_ms=latency_ms,
            )

        except Exception as e:
            latency_ms = int((time.monotonic() - start) * 1000)
            logger.error(f"Google Managed adapter unexpected error: {e}", exc_info=True)
            return TransportResult(
                success=False,
                error=f"Google Managed MCP call failed: {str(e)[:200]}",
                latency_ms=latency_ms,
            )

    async def _get_gcp_adc_token(self) -> str | None:
        """获取 GCP Application Default Credentials Token。

        优先级:
        1. GOOGLE_APPLICATION_CREDENTIALS 环境变量指向的 Service Account JSON
        2. ~/.config/gcloud/application_default_credentials.json
        3. Compute Engine / GKE metadata service

        Returns:
            str | None GCP 访问 Token 或 None（失败时）
        """
        try:
            # P3: 简化实现，从环境变量或默认凭证文件读取
            # P4: 可集成 google-auth library 实现完整 ADC 流程

            import os

            # 检查环境变量
            creds_path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
            if creds_path and os.path.isfile(creds_path):
                # 从 Service Account JSON 提取 token（需要实际调用 OAuth API）
                # P3 简化：假设已有 token 环境变量 GOOGLE_MCP_TOKEN
                token = os.getenv("GOOGLE_MCP_TOKEN", "")
                if token:
                    return token
                else:
                    logger.warning("GOOGLE_APPLICATION_CREDENTIALS set but GOOGLE_MCP_TOKEN not found. "
                                 "P4 will implement full OAuth flow.")
                    return None

            # 检查默认凭证文件（简化版）
            default_creds = os.path.expanduser("~/.config/gcloud/application_default_credentials.json")
            if os.path.isfile(default_creds):
                # P3 简化：假设文件中有 access_token
                # 实际生产需要调用 google.auth 库刷新 token
                try:
                    with open(default_creds) as f:
                        creds_data = json.load(f)
                        token = creds_data.get("access_token", "")
                        if token:
                            return token
                except (json.JSONDecodeError, IOError) as e:
                    logger.warning(f"Failed to read default credentials: {e}")

            logger.warning("No valid GCP ADC found. Set GOOGLE_MCP_TOKEN or GOOGLE_APPLICATION_CREDENTIALS.")
            return None

        except Exception as e:
            logger.error(f"Error obtaining GCP ADC token: {e}", exc_info=True)
            return None

    def _parse_iam_error(self, resp: httpx.Response) -> str:
        """解析 IAM 403 错误详细信息。

        Google IAM 错误格式:
        {
            "error": {
                "code": 403,
                "message": "Permission 'mcp.tools.call' denied on resource '...'",
                "status": "PERMISSION_DENIED"
            }
        }

        Args:
            resp: HTTP 响应对象

        Returns:
            str 用户友好的权限不足提示
        """
        try:
            error_data = resp.json()
            error_msg = error_data.get("error", {}).get("message", "")

            if "mcp.tools.call" in error_msg:
                return ("Missing IAM permission: mcp.tools.call. "
                        "Grant the Service Account 'roles/mcp.toolInvoker' role.")

            return error_msg[:200] if error_msg else "Permission denied (no detail message)"

        except json.JSONDecodeError:
            return resp.text[:200] if resp.text else "Permission denied (parse error)"

    async def validate_auth(self, auth_config: dict[str, Any]) -> bool:
        """验证 Google Managed MCP 认证配置是否有效。

        验证逻辑:
        1. 检查 server_id 是否存在
        2. 检查能否获取 GCP ADC Token
        """
        server_id = auth_config.get("server_id", "")

        if not server_id:
            logger.warning("Google Managed auth validation failed: missing server_id")
            return False

        # 检查能否获取 token
        token = await self._get_gcp_adc_token()
        if not token:
            logger.warning("Google Managed auth validation failed: no valid ADC token")
            return False

        return True