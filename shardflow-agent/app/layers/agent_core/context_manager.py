import time
from typing import Any


class ContextManager:
    """Manages token budget, sliding window, context compression, and pressure thresholds.

    Three pressure levels for cross-session continuation:
    - WARNING (60%): light toast, user can switch or ignore
    - CRITICAL (80%): emphasized toast, user can switch or ignore
    - FULL (100%): blocking modal, user must switch or end task

    Each level fires once; resets when usage drops 5% below the threshold.
    """

    MAX_CONTEXT_TOKENS: int = 128000
    RESERVED_OUTPUT: int = 4096
    SAFETY_MARGIN: float = 0.10
    COMPRESS_THRESHOLD: float = 0.70
    SHARD_THRESHOLD: float = 0.80

    # Three-tier context pressure thresholds
    PRESSURE_WARNING: float = 0.60
    PRESSURE_CRITICAL: float = 0.80
    PRESSURE_FULL: float = 1.0

    COOLDOWN_RESET_MARGIN: float = 0.05  # Must drop 5% below threshold to reset

    def __init__(self) -> None:
        self._cooldown: dict[str, bool] = {
            "warning": False,
            "critical": False,
            "full": False,
        }

    def estimate_tokens(self, messages: list[dict[str, Any]]) -> int:
        total = 0
        for msg in messages:
            content = msg.get("content", "")
            total += len(content) // 4
        return total

    def _usable_tokens(self) -> int:
        return int(self.MAX_CONTEXT_TOKENS * (1.0 - self.SAFETY_MARGIN)) - self.RESERVED_OUTPUT

    def check_budget(self, state: dict[str, Any]) -> bool:
        token_count: int = state.get("token_count", 0)
        usable = self._usable_tokens()
        return token_count < usable

    def get_context_usage(self, state: dict[str, Any]) -> float:
        token_count: int = state.get("token_count", 0)
        usable = self._usable_tokens()
        if usable <= 0:
            return 1.0
        ratio = token_count / usable
        return min(float(ratio), 1.0)

    def get_pressure_level(self, state: dict[str, Any]) -> str | None:
        """Return the current pressure level string, or None if below all thresholds.

        Respects cooldown: each level only fires once until usage drops below
        (threshold - COOLDOWN_RESET_MARGIN).
        """
        usage = self.get_context_usage(state)

        if usage >= self.PRESSURE_FULL and not self._cooldown["full"]:
            self._cooldown["full"] = True
            return "full"

        if usage >= self.PRESSURE_CRITICAL and not self._cooldown["critical"]:
            self._cooldown["critical"] = True
            return "critical"

        if usage >= self.PRESSURE_WARNING and not self._cooldown["warning"]:
            self._cooldown["warning"] = True
            return "warning"

        # Reset cooldowns when usage drops below (threshold - margin)
        self._update_cooldowns(usage)
        return None

    def _update_cooldowns(self, usage: float) -> None:
        if self._cooldown["warning"] and usage < (self.PRESSURE_WARNING - self.COOLDOWN_RESET_MARGIN):
            self._cooldown["warning"] = False
        if self._cooldown["critical"] and usage < (self.PRESSURE_CRITICAL - self.COOLDOWN_RESET_MARGIN):
            self._cooldown["critical"] = False
        if self._cooldown["full"] and usage < (self.PRESSURE_FULL - self.COOLDOWN_RESET_MARGIN):
            self._cooldown["full"] = False

    def manage_window(self, messages: list[dict[str, Any]], max_recent: int = 10) -> list[dict[str, Any]]:
        if len(messages) <= max_recent:
            return messages
        return messages[-max_recent:]

    def should_compress(self, state: dict[str, Any]) -> bool:
        return self.get_context_usage(state) >= self.COMPRESS_THRESHOLD

    def should_shard(self, state: dict[str, Any]) -> bool:
        return self.get_context_usage(state) >= self.SHARD_THRESHOLD

    def summarize_history(self, messages: list[dict[str, Any]]) -> str:
        parts: list[str] = []
        for msg in messages:
            content = msg.get("content", "")
            if content:
                parts.append(content[:200])
        return " | ".join(parts)


context_manager = ContextManager()
