from typing import Any

from app.layers.agent_core.context_manager import context_manager


class ShardDecisionGate:
    def should_shard(self, state: dict[str, Any]) -> bool:
        """Unified shard decision: ContextManager threshold + pending items check.

        Consistent with ContextManager.should_shard(): checks context_usage >= 0.80.
        Additionally ensures there are pending items worth extracting.
        """
        usage = state.get("context_usage_ratio", 0)
        if usage < 0.80:
            return False
        pending = state.get("pending", [])
        return bool(pending and len(pending) > 0)

    def token_budget(self, state: dict[str, Any]) -> int:
        current: int = state.get("token_count", 0)
        usable: int = int(context_manager.MAX_CONTEXT_TOKENS * (1.0 - context_manager.SAFETY_MARGIN))
        remaining: int = usable - current - context_manager.RESERVED_OUTPUT
        return max(remaining, 0)

    def depth_advisor(self, state: dict[str, Any]) -> str:
        """返回通用分析深度建议：OVERVIEW/DETAIL/DEEP_DIVE。

        优先使用用户画像偏好，其次根据 pending 数量推断。
        """
        # 优先读取用户画像中的偏好设置
        user_context = state.get("user_context") or {}
        preferred = user_context.get("preferred_depth", "")
        if preferred in ("OVERVIEW", "DETAIL", "DEEP_DIVE"):
            return preferred

        # 根据 pending 数量推断深度
        pending = state.get("pending", [])
        count = len(pending) if pending else 0
        if count <= 2:
            return "OVERVIEW"
        elif count <= 5:
            return "DETAIL"
        else:
            return "DEEP_DIVE"


shard_decision_gate = ShardDecisionGate()
