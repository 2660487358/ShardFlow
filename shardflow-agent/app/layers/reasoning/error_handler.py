from enum import Enum
from typing import Any


class ErrorCategory(str, Enum):
    RETRYABLE = "retryable"
    CLARIFICATION_NEEDED = "clarification_needed"
    DEGRADABLE = "degradable"
    FATAL = "fatal"


class ErrorHandler:
    """Classifies and handles errors during the ReAct loop."""

    MAX_LOOP_COUNT: int = 15

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
        state["error"] = str(error)
        state["is_done"] = True
        state["final_answer"] = f"推理过程中遇到错误：{error}。已完成 {state.get('loop_count', 0)} 步推理。"
        return state


error_handler = ErrorHandler()
