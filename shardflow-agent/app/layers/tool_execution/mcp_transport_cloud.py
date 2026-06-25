"""L5 Tool Execution: MCP 云托管传输协议分发器。

P3 阶段实现:
- 支持多云提供商路由分发
- 按 connection.provider 选择对应适配器
- 未来可扩展注册 aws-managed、cdata、azure-appservice
"""
import logging
from typing import Any

from app.layers.tool_execution.mcp_cloud_base import CloudProviderAdapter
from app.layers.tool_execution.mcp_cloud_smithery import SmitheryAdapter
from app.layers.tool_execution.mcp_cloud_google import GoogleManagedAdapter
from app.layers.tool_execution.mcp_transport_base import BaseTransport, TransportResult

logger = logging.getLogger(__name__)


class CloudTransport(BaseTransport):
    """云托管 MCP 传输协议适配器。

    按 connection.provider 分发到具体平台适配器。

    支持的 Provider:
    - smithery: Smithery 社区 MCP Server
    - google-managed: Google Cloud Managed MCP

    未来扩展:
    - aws-managed: AWS MCP Server
    - cdata: CData Connect AI
    - azure-appservice: Azure App Service MCP
    """

    def __init__(self) -> None:
        # Provider 适配器注册表
        self._adapters: dict[str, CloudProviderAdapter] = {
            "smithery": SmitheryAdapter(),
            "google-managed": GoogleManagedAdapter(),
        }

    def protocol_name(self) -> str:
        return "cloud"

    async def call_tool(
        self,
        server_url: str,
        tool_name: str,
        arguments: dict[str, Any],
        timeout_seconds: int = 30,
        auth_config: dict[str, Any] | None = None,
    ) -> TransportResult:
        """通过云托管传输协议调用 MCP 工具。

        Args:
            server_url: 云模式下承载 provider 标识 (如 "smithery", "google-managed")
            tool_name: 工具名称
            arguments: 调用参数
            timeout_seconds: 超时时间（秒）
            auth_config: 认证配置（包含 api_key、server_key、server_id 等）

        Returns:
            TransportResult 传输层调用结果
        """
        provider = server_url  # cloud 模式下 server_url 承载 provider 标识

        # 查找适配器
        adapter = self._adapters.get(provider)
        if not adapter:
            supported = ", ".join(sorted(self._adapters.keys()))
            return TransportResult(
                success=False,
                error=f"Unsupported cloud provider: '{provider}'. Supported providers: {supported}",
            )

        logger.info(f"Routing MCP call to {provider} adapter: tool={tool_name}")

        # 委托适配器调用
        return await adapter.call_tool(
            tool_name,
            arguments,
            timeout_seconds,
            auth_config,
        )

    async def close(self) -> None:
        """关闭传输连接，释放资源。

        Cloud 模式下无需维护持久连接，各适配器内部使用 httpx.AsyncClient，
        每次调用后自动关闭。
        """
        logger.debug("CloudTransport.close() called - no persistent connections to close")

    def register_adapter(self, provider: str, adapter: CloudProviderAdapter) -> None:
        """注册新的云提供商适配器（动态扩展）。

        Args:
            provider: 提供商名称（如 "aws-managed", "cdata"）
            adapter: 适配器实例

        Example:
            transport.register_adapter("aws-managed", AwsManagedAdapter())
        """
        if provider in self._adapters:
            logger.warning(f"Overriding existing adapter for provider: {provider}")

        self._adapters[provider] = adapter
        logger.info(f"Registered cloud provider adapter: {provider} -> {adapter.provider_name()}")

    def get_supported_providers(self) -> list[str]:
        """获取当前支持的云提供商列表。"""
        return sorted(self._adapters.keys())