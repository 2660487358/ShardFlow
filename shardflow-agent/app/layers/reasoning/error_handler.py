from enum import Enum
from typing import Any


class ErrorCategory(str, Enum):
    RETRYABLE = "retryable"
    CLARIFICATION_NEEDED = "clarification_needed"
    DEGRADABLE = "degradable"
    FATAL = "fatal"


class ErrorHandler:
    """Classifies and handles errors during the ReAct loop.

    企业级Agent模型输出行为规范: 错误信息不得暴露内部状态（循环次数、错误堆栈等）。
    """

    MAX_LOOP_COUNT: int = 15

    # 用户可见的降级话术（不暴露内部状态）
    _FALLBACK_MESSAGES = {
        "timeout": "响应超时，请稍后重试。",
        "rate_limit": "当前请求较频繁，请稍后重试。",
        "server_error": "服务暂时不可用，请稍后重试。",
        "auth_error": "认证失败，请重新登录。",
        "loop_limit": "已为您整理当前可获得的信息。如需更详细的分析，请继续提问。",
        "default": "系统处理中，请稍候重试。",
    }

    def classify_error(self, error: Exception) -> ErrorCategory:
        name = type(error).__name__.lower()
        msg = str(error).lower()

        if "timeout" in name or "timeout" in msg:
            return ErrorCategory.RETRYABLE
        if "429" in msg or "rate" in msg or "limit" in msg:
            return ErrorCategory.RETRYABLE
        if "format" in msg or "json" in msg or "schema" in msg:
            return ErrorCategory.RETRYABLE
        if "auth" in msg or "401" in msg or "403" in msg:
            return ErrorCategory.FATAL
        if "500" in msg or "server" in msg:
            return ErrorCategory.DEGRADABLE

        return ErrorCategory.FATAL

    def handle_llm_error(self, error: Exception, retries_left: int) -> dict[str, Any]:
        category = self.classify_error(error)
        if category == ErrorCategory.RETRYABLE and retries_left > 0:
            return {"action": "retry", "retries_left": retries_left - 1}
        if category == ErrorCategory.DEGRADABLE:
            return {"action": "degrade", "fallback_model": "gpt-4o-mini"}
        return {"action": "fail", "error": str(error)}

    def handle_tool_error(self, error: Exception) -> dict[str, Any]:
        category = self.classify_error(error)
        if category == ErrorCategory.RETRYABLE:
            return {"action": "skip", "reason": f"跳过工具：{error}"}
        return {"action": "skip", "reason": f"工具失败：{error}"}

    def handle_loop_limit(self, state: dict[str, Any]) -> bool:
        loop_count: int = state.get("loop_count", 0)
        return loop_count >= self.MAX_LOOP_COUNT

    def format_error_state(self, state: dict[str, Any], error: Exception) -> dict[str, Any]:
        """Format error state with user-safe messages (no internal state exposure)."""
        state["error"] = str(error)
        state["is_done"] = True

        # 根据错误类型选择用户可见的降级话术，不暴露内部状态
        msg = str(error).lower()
        if "timeout" in msg:
            state["final_answer"] = self._FALLBACK_MESSAGES["timeout"]
        elif "429" in msg or "rate" in msg:
            state["final_answer"] = self._FALLBACK_MESSAGES["rate_limit"]
        elif "500" in msg or "server" in msg:
            state["final_answer"] = self._FALLBACK_MESSAGES["server_error"]
        elif "auth" in msg or "401" in msg or "403" in msg:
            state["final_answer"] = self._FALLBACK_MESSAGES["auth_error"]
        else:
            state["final_answer"] = self._FALLBACK_MESSAGES["default"]

        return state

    def format_loop_limit_state(self, state: dict[str, Any]) -> dict[str, Any]:
        """Format loop limit reached state with user-safe message."""
        state["is_done"] = True
        state["final_answer"] = self._FALLBACK_MESSAGES["loop_limit"]
        return state


error_handler = ErrorHandler()
