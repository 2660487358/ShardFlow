"""L6 Security Layer: MCPSecurityGateway — MCP 工具调用安全网关。

在 MCP 工具调用前执行：
1. 权限校验：检查工具调用权限
2. 频率限制：防止滥用（token bucket）
3. 操作审计：记录所有 MCP 调用
4. 参数过滤：清理敏感/危险参数
"""
import asyncio
import logging
import time
from typing import Any

logger = logging.getLogger(__name__)


class TokenBucket:
    """简单令牌桶限流器。"""
    def __init__(self, rate: float, burst: int):
        self._rate = rate
        self._burst = burst
        self._tokens = float(burst)
        self._last_refill = time.monotonic()
        self._lock = asyncio.Lock()

    async def acquire(self) -> bool:
        async with self._lock:
            now = time.monotonic()
            elapsed = now - self._last_refill
            self._tokens = min(self._burst, self._tokens + elapsed * self._rate)
            self._last_refill = now
            if self._tokens >= 1.0:
                self._tokens -= 1.0
                return True
            return False


class MCPSecurityGateway:
    """MCP 安全网关 — 权限校验、频率限制、审计、参数过滤。"""

    # 默认权限矩阵：工具 → 所需权限列表
    DEFAULT_PERMISSIONS: dict[str, list[str]] = {
        "web_search": ["search:read"],
        "read_file": ["repo:read"],
        "write_file": ["repo:write"],
        "code_analyze": ["repo:read"],
        "feishu_send": ["message:send"],
        "feishu_read": ["message:read"],
        "dingtalk_send": ["message:send"],
        "calendar_read": ["calendar:read"],
        "calendar_write": ["calendar:write"],
        "todo_create": ["task:write"],
        "todo_read": ["task:read"],
    }

    # 工具 → 频率限制 (calls per minute)
    DEFAULT_RATE_LIMITS: dict[str, tuple[float, int]] = {
        "web_search": (10.0, 5),     # 10 req/min, burst 5
        "feishu_send": (20.0, 10),   # 20 req/min, burst 10
        "dingtalk_send": (20.0, 10),
        "calendar_write": (30.0, 15),
    }

    def __init__(self) -> None:
        self._buckets: dict[str, TokenBucket] = {}
        self._audit_log: list[dict[str, Any]] = []

    def validate_permission(self, tool_name: str, user_permissions: list[str]) -> bool:
        """校验工具调用权限。

        Args:
            tool_name: 工具名称
            user_permissions: 用户拥有的权限列表

        Returns:
            是否有权限调用
        """
        required = self.DEFAULT_PERMISSIONS.get(tool_name, [])
        if not required:
            return True  # 无需特殊权限

        for perm in required:
            if perm in user_permissions:
                return True
        logger.warning(f"Permission denied: {tool_name} requires {required}, user has {user_permissions}")
        return False

    async def check_rate_limit(self, tool_name: str) -> bool:
        """检查频率限制。

        Returns:
            True 表示允许调用，False 表示被限流
        """
        rate_limit = self.DEFAULT_RATE_LIMITS.get(tool_name)
        if rate_limit is None:
            return True  # 无限流限制

        rate, burst = rate_limit
        if tool_name not in self._buckets:
            self._buckets[tool_name] = TokenBucket(rate, burst)

        if not await self._buckets[tool_name].acquire():
            logger.warning(f"Rate limit exceeded for {tool_name}")
            return False
        return True

    def sanitize_params(self, tool_name: str, params: dict[str, Any]) -> dict[str, Any]:
        """清理敏感/危险参数。

        移除或转义可能危险的值（SQL 注入、路径遍历等）。
        """
        sanitized = {}
        dangerous_patterns = ["../", "DROP ", "DELETE ", "--", ";", "|"]

        for key, value in params.items():
            if isinstance(value, str):
                cleaned = value
                for pattern in dangerous_patterns:
                    if pattern in cleaned:
                        cleaned = cleaned.replace(pattern, f"[FILTERED:{pattern.strip()}]")
                sanitized[key] = cleaned
            else:
                sanitized[key] = value

        return sanitized

    def audit_call(self, user_id: str, tool_name: str, params: dict[str, Any],
                   success: bool, error: str = "", latency_ms: int = 0) -> None:
        """记录 MCP 工具调用审计日志。"""
        entry = {
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "user_id": user_id,
            "tool_name": tool_name,
            "params_summary": str(params)[:200],
            "success": success,
            "error": error[:200] if error else "",
            "latency_ms": latency_ms,
        }
        self._audit_log.append(entry)
        # 限制审计日志大小
        if len(self._audit_log) > 10000:
            self._audit_log = self._audit_log[-5000:]
        logger.info(f"MCP Audit: user={user_id}, tool={tool_name}, success={success}")

    async def gate_call(self, user_id: str, tool_name: str, params: dict[str, Any],
                        user_permissions: list[str] | None = None) -> tuple[bool, dict[str, Any], str]:
        """安全网关入口 — 权限校验 → 频率检查 → 参数过滤。

        Returns:
            (allowed, sanitized_params, rejection_reason)
        """
        # 1. 权限校验
        if not self.validate_permission(tool_name, user_permissions or []):
            self.audit_call(user_id, tool_name, params, False, "Permission denied")
            return False, params, "Permission denied"

        # 2. 频率检查
        if not await self.check_rate_limit(tool_name):
            self.audit_call(user_id, tool_name, params, False, "Rate limit exceeded")
            return False, params, "Rate limit exceeded"

        # 3. 参数过滤
        sanitized = self.sanitize_params(tool_name, params)

        return True, sanitized, ""


mcp_security_gateway = MCPSecurityGateway()
