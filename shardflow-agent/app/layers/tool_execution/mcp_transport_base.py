"""L5 Tool Execution: MCP 传输协议抽象基类。

P6 阶段实现 (FR-CONN-002):
- 定义 MCP 传输协议统一接口
- 支持 HTTP-SSE 和 stdio 两种传输协议
- 传输层与业务逻辑解耦
"""
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class TransportResult:
    """传输层调用结果。"""
    success: bool
    data: dict[str, Any] = field(default_factory=dict)
    error: str = ""
    status_code: int | None = None
    latency_ms: int = 0


class BaseTransport(ABC):
    """MCP 传输协议抽象基类。

    所有传输协议实现必须继承此类并实现 call_tool 方法。
    """

    @abstractmethod
    async def call_tool(
        self,
        server_url: str,
        tool_name: str,
        arguments: dict[str, Any],
        timeout_seconds: int = 30,
        auth_config: dict[str, Any] | None = None,
    ) -> TransportResult:
        """通过传输协议调用 MCP 工具。

        Args:
            server_url: MCP Server 地址
            tool_name: 工具名称
            arguments: 调用参数
            timeout_seconds: 超时时间（秒）
            auth_config: 认证配置（可选）

        Returns:
            TransportResult 传输层调用结果
        """
        ...

    @abstractmethod
    async def close(self) -> None:
        """关闭传输连接，释放资源。"""
        ...

    @abstractmethod
    def protocol_name(self) -> str:
        """返回传输协议名称。"""
        ...
