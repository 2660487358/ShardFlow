"""L5 Tool Execution: MCP 云托管提供商适配器抽象基类。

P3 阶段实现:
- 定义云托管 MCP 提供商统一接口
- 支持多云提供商接入 (Smithery, Google Managed MCP, AWS, CData, Azure)
- 抽象认证、调用、错误处理逻辑
"""
import logging
from abc import ABC, abstractmethod
from typing import Any

from app.layers.tool_execution.mcp_transport_base import TransportResult

logger = logging.getLogger(__name__)


class CloudProviderAdapter(ABC):
    """云托管 MCP 提供商适配器抽象基类。

    所有云托管提供商实现必须继承此类并实现相应方法。
    """

    @abstractmethod
    async def call_tool(
        self,
        tool_name: str,
        arguments: dict[str, Any],
        timeout_seconds: int = 30,
        auth_config: dict[str, Any] | None = None,
    ) -> TransportResult:
        """调用云托管 MCP 工具。

        Args:
            tool_name: 工具名称
            arguments: 调用参数
            timeout_seconds: 超时时间（秒）
            auth_config: 认证配置（包含 api_key、server_key 等）

        Returns:
            TransportResult 传输层调用结果
        """
        ...

    @abstractmethod
    def protocol_name(self) -> str:
        """返回传输协议名称。"""
        ...

    @abstractmethod
    def provider_name(self) -> str:
        """返回云提供商名称。"""
        ...

    @abstractmethod
    async def validate_auth(self, auth_config: dict[str, Any]) -> bool:
        """验证认证配置是否有效。

        Args:
            auth_config: 认证配置

        Returns:
            bool 认证配置是否有效
        """
        ...

    def _extract_mcp_content(self, response_data: dict[str, Any]) -> dict[str, Any]:
        """从 MCP 标准响应中提取内容。

        MCP 标准响应格式:
        {
            "content": [
                {"type": "text", "text": "..."}
            ]
        }

        Args:
            response_data: 原始响应数据

        Returns:
            dict 提取后的内容数据
        """
        content = response_data.get("content")
        if content and isinstance(content, list):
            # 提取所有文本内容
            text_parts: list[str] = []
            for item in content:
                if isinstance(item, dict) and item.get("type") == "text":
                    text_parts.append(str(item.get("text", "")))

            if text_parts:
                return {"content": "\n".join(text_parts)}

        # 如果不是标准格式，返回原始数据
        return response_data
