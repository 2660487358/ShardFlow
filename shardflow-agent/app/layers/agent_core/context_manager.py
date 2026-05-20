from typing import Any


class ContextManager:
    """Manages token budget, sliding window, and context compression."""

    MAX_CONTEXT_TOKENS: int = 128000
    RESERVED_OUTPUT: int = 4096
    SAFETY_MARGIN: float = 0.10
    COMPRESS_THRESHOLD: float = 0.70
    SHARD_THRESHOLD: float = 0.80

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
