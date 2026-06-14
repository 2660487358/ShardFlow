"""L6 Security Layer: MCPSecurityGateway — MCP 工具调用安全网关。

P5 阶段增强，新增：
1. 高风险工具用户确认 (SEC-TOOL-001)
2. 有副作用工具授权 (SEC-TOOL-002)
3. 工具调用错误友好提示 (SEC-TOOL-004)
4. 权限校验：检查工具调用权限
5. 频率限制：防止滥用（token bucket）
6. 操作审计：记录所有 MCP 调用
7. 参数过滤：清理敏感/危险参数
"""
import asyncio
import logging
import time
from dataclasses import dataclass, field
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


@dataclass
class SecurityGateResult:
    """安全网关校验结果。"""
    allowed: bool
    sanitized_params: dict[str, Any]
    rejection_reason: str = ""
    requires_confirmation: bool = False  # SEC-TOOL-001: 需要用户确认
    confirmation_message: str = ""       # SEC-TOOL-001: 确认提示消息
    requires_authorization: bool = False  # SEC-TOOL-002: 需要用户授权
    authorization_message: str = ""       # SEC-TOOL-002: 授权提示消息


class MCPSecurityGateway:
    """MCP 安全网关 — 权限校验、频率限制、审计、参数过滤、安全确认。"""

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

    # SEC-TOOL-002: 有副作用的工具（写操作）需要授权
    SIDE_EFFECT_PERMISSIONS: set[str] = {
        "repo:write", "message:send", "calendar:write",
        "task:write", "doc:write", "file:write",
    }

    # SEC-TOOL-004: 友好错误消息映射
    FRIENDLY_ERROR_MESSAGES: dict[str, str] = {
        "Permission denied": "您没有使用此工具的权限，请联系管理员。",
        "Rate limit exceeded": "操作过于频繁，请稍后再试。",
        "timeout": "工具响应超时，请稍后重试。",
        "connection": "无法连接到工具服务，请检查网络或稍后重试。",
        "MCP tool not found": "未找到指定的工具，请确认工具名称是否正确。",
        "MCP tool": "工具当前不可用，请稍后重试。",
    }

    def __init__(self) -> None:
        self._buckets: dict[str, TokenBucket] = {}
        self._audit_log: list[dict[str, Any]] = []
        # SEC-TOOL-001: 用户确认回调（由上层设置）
        self._confirmation_callback: Any = None
        # SEC-TOOL-002: 用户授权回调（由上层设置）
        self._authorization_callback: Any = None

    def set_confirmation_callback(self, callback: Any) -> None:
        """设置高风险工具用户确认回调 (SEC-TOOL-001)。
        回调签名: async (message: str) -> bool
        返回 True 表示用户确认执行，False 表示拒绝。
        """
        self._confirmation_callback = callback

    def set_authorization_callback(self, callback: Any) -> None:
        """设置有副作用工具授权回调 (SEC-TOOL-002)。
        回调签名: async (message: str) -> bool
        返回 True 表示用户授权执行，False 表示拒绝。
        """
        self._authorization_callback = callback

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

        # SEC-AUTH-003: AND 语义 — 用户必须拥有工具所需的全部权限
        for perm in required:
            if perm not in user_permissions:
                logger.warning(f"Permission denied: {tool_name} requires {required}, user has {user_permissions}")
                return False
        return True

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

    def check_high_risk(self, tool_name: str, risk_level: str) -> tuple[bool, str]:
        """检查高风险工具 (SEC-TOOL-001)。

        Returns:
            (is_high_risk, confirmation_message)
        """
        if risk_level == "high":
            message = (
                f"⚠️ 即将调用高风险工具 [{tool_name}]，该工具可能产生不可逆的操作。\n"
                f"请确认是否继续执行？"
            )
            return True, message
        return False, ""

    def check_side_effects(self, tool_name: str, permissions: list[str] | None) -> tuple[bool, str]:
        """检查有副作用的工具 (SEC-TOOL-002)。

        通过 permissions 字段中包含 write/send/create/delete 等关键词判断。

        Returns:
            (has_side_effects, authorization_message)
        """
        if not permissions:
            return False, ""

        for perm in permissions:
            if perm in self.SIDE_EFFECT_PERMISSIONS:
                action = perm.split(":")[-1] if ":" in perm else perm
                message = (
                    f"🔐 工具 [{tool_name}] 需要执行写操作 ({action})，\n"
                    f"请授权此操作。"
                )
                return True, message
        return False, ""

    def get_friendly_error(self, error: str) -> str:
        """将内部错误转换为友好提示 (SEC-TOOL-004)。

        不暴露内部错误详情给用户。
        """
        if not error:
            return "操作失败，请稍后重试。"

        for key, friendly_msg in self.FRIENDLY_ERROR_MESSAGES.items():
            if key.lower() in error.lower():
                return friendly_msg

        # 默认友好提示，不暴露内部错误详情
        return "操作未能完成，请稍后重试或联系管理员。"

    async def gate_call(self, user_id: str, tool_name: str, params: dict[str, Any],
                        user_permissions: list[str] | None = None,
                        risk_level: str = "low",
                        tool_permissions: list[str] | None = None) -> SecurityGateResult:
        """安全网关入口 — 权限校验 → 频率检查 → 参数过滤 → 安全确认。

        P5 阶段增强：新增高风险确认和副作用授权检查。

        Returns:
            SecurityGateResult 包含校验结果和安全确认信息
        """
        # 1. 权限校验
        if not self.validate_permission(tool_name, user_permissions or []):
            self.audit_call(user_id, tool_name, params, False, "Permission denied")
            return SecurityGateResult(
                allowed=False,
                sanitized_params=params,
                rejection_reason="Permission denied",
            )

        # 2. 频率检查
        if not await self.check_rate_limit(tool_name):
            self.audit_call(user_id, tool_name, params, False, "Rate limit exceeded")
            return SecurityGateResult(
                allowed=False,
                sanitized_params=params,
                rejection_reason="Rate limit exceeded",
            )

        # 3. 参数过滤
        sanitized = self.sanitize_params(tool_name, params)

        # 4. SEC-TOOL-001: 高风险工具用户确认
        is_high_risk, confirmation_msg = self.check_high_risk(tool_name, risk_level)
        if is_high_risk and self._confirmation_callback:
            confirmed = await self._confirmation_callback(confirmation_msg)
            if not confirmed:
                self.audit_call(user_id, tool_name, params, False, "User declined high-risk confirmation")
                return SecurityGateResult(
                    allowed=False,
                    sanitized_params=sanitized,
                    rejection_reason="User declined high-risk confirmation",
                )

        # 5. SEC-TOOL-002: 有副作用工具授权
        has_side_effects, auth_msg = self.check_side_effects(tool_name, tool_permissions)
        if has_side_effects and self._authorization_callback:
            authorized = await self._authorization_callback(auth_msg)
            if not authorized:
                self.audit_call(user_id, tool_name, params, False, "User declined side-effect authorization")
                return SecurityGateResult(
                    allowed=False,
                    sanitized_params=sanitized,
                    rejection_reason="User declined side-effect authorization",
                )

        result = SecurityGateResult(
            allowed=True,
            sanitized_params=sanitized,
            requires_confirmation=is_high_risk,
            confirmation_message=confirmation_msg,
            requires_authorization=has_side_effects,
            authorization_message=auth_msg,
        )

        return result


mcp_security_gateway = MCPSecurityGateway()
