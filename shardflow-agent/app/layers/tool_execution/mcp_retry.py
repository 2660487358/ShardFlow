"""L5 Tool Execution: MCPRetry — MCP 工具调用重试机制。

实现规格文档 FR-INVOKE-004:
- 默认重试 1 次，可按工具配置
- 重试间隔 1 秒
- 重试失败后降级处理
- 仅对可重试错误重试（网络超时、服务端 5xx）
- 不对 4xx 客户端错误重试
"""
import asyncio
import logging
from typing import Any, Callable

import httpx

from app.layers.agent_core.mcp_client import MCPCallResult

logger = logging.getLogger(__name__)

# 最大重试等待时间（秒）
_MAX_DELAY_SECONDS = 5.0


class MCPRetryPolicy:
    """MCP 工具调用重试策略。

    根据 FR-INVOKE-004 规格要求，仅对可重试错误进行重试：
    - 网络超时（httpx.TimeoutException / asyncio.TimeoutError）
    - 连接错误（httpx.ConnectError）
    - 服务端 5xx 错误
    不对 4xx 客户端错误重试。
    """

    def __init__(
        self,
        max_retries: int = 1,
        retry_delay_seconds: float = 1.0,
        retryable_status_codes: set[int] | None = None,
    ) -> None:
        self.max_retries = max_retries
        self.retry_delay_seconds = retry_delay_seconds
        self.retryable_status_codes: set[int] = retryable_status_codes or {500, 502, 503, 504}

    def should_retry(
        self,
        attempt: int,
        error: Exception | None = None,
        status_code: int | None = None,
    ) -> bool:
        """判断是否应该重试。

        Args:
            attempt: 当前已尝试次数（从 1 开始）。
            error: 调用抛出的异常。
            status_code: HTTP 响应状态码。

        Returns:
            True 表示应重试，False 表示不应重试。
        """
        if attempt > self.max_retries:
            return False

        # 4xx 客户端错误不可重试
        if status_code is not None and 400 <= status_code < 500:
            return False

        # 5xx 或在可重试状态码集合中
        if status_code is not None and (
            500 <= status_code < 600 or status_code in self.retryable_status_codes
        ):
            return True

        # 超时异常可重试
        if error is not None and isinstance(error, (httpx.TimeoutException, asyncio.TimeoutError)):
            return True

        # 连接错误可重试
        if error is not None and isinstance(error, httpx.ConnectError):
            return True

        return False

    def get_retry_delay(self, attempt: int) -> float:
        """计算重试等待时间（指数退避）。

        Args:
            attempt: 当前重试次数（从 1 开始）。

        Returns:
            等待秒数，最大不超过 _MAX_DELAY_SECONDS。
        """
        delay = self.retry_delay_seconds * (2 ** (attempt - 1))
        return min(delay, _MAX_DELAY_SECONDS)

    async def wait_before_retry(self, attempt: int) -> None:
        """在重试前异步等待。

        Args:
            attempt: 当前重试次数（从 1 开始）。
        """
        delay = self.get_retry_delay(attempt)
        logger.debug(f"Retry attempt {attempt}, waiting {delay:.1f}s")
        await asyncio.sleep(delay)


async def execute_with_retry(
    call_fn: Callable,
    tool_name: str,
    max_retries: int = 1,
    retry_delay: float = 1.0,
) -> Any:
    """带重试机制地执行 MCP 工具调用。

    执行 call_fn，若失败且满足重试条件则等待后重试，
    直到成功或重试次数耗尽返回最终结果。

    Args:
        call_fn: 异步可调用对象，返回 MCPCallResult。
        tool_name: 工具名称，用于日志记录。
        max_retries: 最大重试次数，默认 1。
        retry_delay: 重试基础间隔秒数，默认 1.0。

    Returns:
        MCPCallResult: 工具调用结果（成功或最终失败）。
    """
    policy = MCPRetryPolicy(
        max_retries=max_retries,
        retry_delay_seconds=retry_delay,
    )

    attempt = 0
    last_result: MCPCallResult | None = None

    while True:
        attempt += 1
        try:
            result: MCPCallResult = await call_fn()
            if result.success:
                return result

            # 调用成功返回但业务失败，尝试从 error 中提取 status_code
            status_code = _extract_status_code(result.error)
            if not policy.should_retry(attempt, status_code=status_code):
                logger.warning(
                    f"MCP tool '{tool_name}' failed (non-retryable), attempt {attempt}: {result.error}"
                )
                return result

            if not policy.should_retry(attempt):
                logger.warning(
                    f"MCP tool '{tool_name}' max retries ({max_retries}) exhausted, attempt {attempt}"
                )
                return result

            logger.info(
                f"MCP tool '{tool_name}' failed, retrying (attempt {attempt}/{max_retries}): {result.error}"
            )
            last_result = result
            await policy.wait_before_retry(attempt)

        except httpx.TimeoutException as exc:
            if not policy.should_retry(attempt, error=exc):
                logger.warning(
                    f"MCP tool '{tool_name}' timeout, max retries exhausted (attempt {attempt})"
                )
                return MCPCallResult(
                    tool_name=tool_name,
                    success=False,
                    error=f"Timeout after {attempt} attempt(s): {exc}",
                )
            logger.info(
                f"MCP tool '{tool_name}' timeout, retrying (attempt {attempt}/{max_retries})"
            )
            await policy.wait_before_retry(attempt)

        except httpx.ConnectError as exc:
            if not policy.should_retry(attempt, error=exc):
                logger.warning(
                    f"MCP tool '{tool_name}' connection error, max retries exhausted (attempt {attempt})"
                )
                return MCPCallResult(
                    tool_name=tool_name,
                    success=False,
                    error=f"Connection error after {attempt} attempt(s): {exc}",
                )
            logger.info(
                f"MCP tool '{tool_name}' connection error, retrying (attempt {attempt}/{max_retries})"
            )
            await policy.wait_before_retry(attempt)

        except Exception as exc:
            if not policy.should_retry(attempt, error=exc):
                logger.warning(
                    f"MCP tool '{tool_name}' error (non-retryable), attempt {attempt}: {exc}"
                )
                return MCPCallResult(
                    tool_name=tool_name,
                    success=False,
                    error=f"Error after {attempt} attempt(s): {exc}",
                )
            logger.info(
                f"MCP tool '{tool_name}' error, retrying (attempt {attempt}/{max_retries}): {exc}"
            )
            await policy.wait_before_retry(attempt)

    # 理论上不可达，但作为安全保障
    return last_result or MCPCallResult(
        tool_name=tool_name,
        success=False,
        error="Retry exhausted with no result",
    )


def _extract_status_code(error_message: str) -> int | None:
    """从错误消息中提取 HTTP 状态码。

    MCPClient.call_tool 在 4xx/5xx 时返回形如
    "MCP server returned 503: ..." 的错误消息，
    本函数从中提取状态码数字。

    Args:
        error_message: 错误消息字符串。

    Returns:
        提取到的状态码整数，或 None。
    """
    if not error_message:
        return None
    import re

    match = re.search(r"returned\s+(\d{3})", error_message)
    if match:
        return int(match.group(1))
    return None
