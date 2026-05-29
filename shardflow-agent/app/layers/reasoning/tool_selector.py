"""L4 Reasoning Layer: ToolSelector — 策略驱动的工具择优。

根据策略历史 + 用户偏好选择最优工具组合（内置 + MCP）。
支持：
- 策略匹配：基于历史策略选择工具组合
- 用户偏好加权：按用户画像偏好调整工具排序
- 成本估算：预估工具调用的时间/Token 成本
- 冷启动降级：无历史策略时使用默认选择
"""
import logging
from typing import Any

logger = logging.getLogger(__name__)


class ToolSelection:
    """工具选择结果。"""
    def __init__(self, tools: list[str], reason: str = "", estimated_cost_ms: int = 0):
        self.tools = tools
        self.reason = reason
        self.estimated_cost_ms = estimated_cost_ms


# 意图 → 默认工具组合（冷启动）
# 格式: [{"name": str, "source": "builtin"|"mcp"}]
DEFAULT_TOOL_COMBOS: dict[str, list[dict[str, str]]] = {
    "research":          [{"name": "web_search", "source": "mcp"}, {"name": "read_file", "source": "builtin"}],
    "web_search":        [{"name": "web_search", "source": "mcp"}],
    "knowledge_qa":      [{"name": "web_search", "source": "mcp"}],
    "write_doc":         [{"name": "read_file", "source": "builtin"}, {"name": "web_search", "source": "mcp"}, {"name": "write_file", "source": "builtin"}],
    "write_code":        [{"name": "read_file", "source": "builtin"}, {"name": "code_analyze", "source": "builtin"}, {"name": "write_file", "source": "builtin"}],
    "task_plan":         [{"name": "web_search", "source": "mcp"}, {"name": "read_file", "source": "builtin"}],
    "schedule":          [{"name": "web_search", "source": "mcp"}],
    "file_op":           [{"name": "read_file", "source": "builtin"}, {"name": "write_file", "source": "builtin"}],
    "code_explore":      [{"name": "read_file", "source": "builtin"}, {"name": "code_analyze", "source": "builtin"}],
    "code_fix":          [{"name": "read_file", "source": "builtin"}, {"name": "code_analyze", "source": "builtin"}],
    "design_proposal":   [{"name": "read_file", "source": "builtin"}, {"name": "code_analyze", "source": "builtin"}, {"name": "web_search", "source": "mcp"}],
    "continue_task":     [{"name": "read_file", "source": "builtin"}],
    "feedback":          [],
    "message_send":      [],
    "notification":      [],
    "general_qa":        [{"name": "web_search", "source": "mcp"}],
}


# 工具成本估算（毫秒）
TOOL_COST_MS: dict[str, int] = {
    "web_search": 2000,
    "read_file": 500,
    "write_file": 800,
    "code_analyze": 1500,
    "extract_shard": 300,
    "query_strategy": 400,
    "save_strategy": 500,
}


class ToolSelector:
    """工具选择器 — 策略驱动 + 偏好加权 + 成本感知。"""

    def __init__(self) -> None:
        pass

    def select_tools(self, intent: str, user_preferences: dict[str, Any] | None = None,
                     strategy_history: list[dict[str, Any]] | None = None) -> ToolSelection:
        """基于意图和策略历史选择最优工具组合。

        优先级:
        1. 历史策略匹配（最高相似度的策略的 tool_combo）
        2. 用户偏好加权（preferred_tools 排序）
        3. 默认降级（DEFAULT_TOOL_COMBOS）
        """
        # 1. 尝试从策略历史匹配
        if strategy_history:
            for strategy in strategy_history:
                if strategy.get("task_type") == intent:
                    tool_combo = strategy.get("tool_combo", [])
                    if isinstance(tool_combo, list) and tool_combo:
                        # 兼容两种格式：新格式 [{name, source}] 和旧格式 ["name"]
                        tool_names = [t if isinstance(t, str) else t.get("name", "") for t in tool_combo]
                        return ToolSelection(
                            tools=tool_names,
                            reason=f"复用历史策略: {strategy.get('strategy_id', 'unknown')}",
                            estimated_cost_ms=sum(TOOL_COST_MS.get(n, 1000) for n in tool_names),
                        )

        # 2. 根据用户偏好工具加权选择
        preferred_tools = (user_preferences or {}).get("preferred_tools", [])
        default_tool_dicts = DEFAULT_TOOL_COMBOS.get(intent, [{"name": "web_search", "source": "mcp"}])
        default_tool_names = [t if isinstance(t, str) else t.get("name", "") for t in default_tool_dicts]

        if preferred_tools:
            ranked = self._rank_by_preference(default_tool_names, preferred_tools)
            return ToolSelection(
                tools=ranked,
                reason=f"基于用户偏好排序: {preferred_tools}",
                estimated_cost_ms=sum(TOOL_COST_MS.get(t, 1000) for t in ranked),
            )

        # 3. 冷启动降级
        return ToolSelection(
            tools=default_tool_names,
            reason="冷启动默认选择",
            estimated_cost_ms=sum(TOOL_COST_MS.get(t, 1000) for t in default_tool_names),
        )

    def _rank_by_preference(self, tools: list[str], preferred: list[str]) -> list[str]:
        """按用户偏好排序工具列表。"""
        pref_set = set(preferred)
        # 偏好工具排前面，其余保持原顺序
        preferred_tools = [t for t in tools if t in pref_set]
        other_tools = [t for t in tools if t not in pref_set]
        return preferred_tools + other_tools

    def estimate_cost(self, tools: list[str]) -> int:
        """估算工具调用的总时间成本（毫秒）。"""
        return sum(TOOL_COST_MS.get(t, 1000) for t in tools)

    def fallback_selection(self, intent: str = "general_qa") -> ToolSelection:
        """无历史策略时的默认选择。"""
        tool_dicts = DEFAULT_TOOL_COMBOS.get(intent, [{"name": "web_search", "source": "mcp"}])
        tools = [t if isinstance(t, str) else t.get("name", "") for t in tool_dicts]
        return ToolSelection(
            tools=tools,
            reason="无历史策略，使用默认工具",
            estimated_cost_ms=self.estimate_cost(tools),
        )


tool_selector = ToolSelector()
