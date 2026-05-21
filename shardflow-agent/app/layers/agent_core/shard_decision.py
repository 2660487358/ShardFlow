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
        pending = state.get("pending", [])
        count = len(pending) if pending else 0
        if count <= 2:
            return "SERVICE_LEVEL"
        elif count <= 5:
            return "METHOD_LEVEL"
        else:
            return "LINE_LEVEL"


shard_decision_gate = ShardDecisionGate()
