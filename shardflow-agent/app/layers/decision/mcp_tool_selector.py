"""L4 Decision Layer: MCPToolSelector — MCP 工具意图匹配选择。

实现规格文档 FR-DISC-005:
- 根据任务意图自动选择合适的 MCP 工具
- 用户可覆盖自动选择的工具
- 匹配策略：关键词匹配 + 分类匹配 + 描述语义匹配
"""
import logging
import re

from app.layers.agent_core.mcp_client import MCPToolInfo

logger = logging.getLogger(__name__)

# 分类 → 关键词映射
CATEGORY_KEYWORDS: dict[str, list[str]] = {
    "communication": ["消息", "飞书", "钉钉", "通讯", "message", "chat", "feishu", "dingtalk"],
    "search": ["搜索", "查询", "检索", "search", "find", "lookup"],
    "code": ["代码", "编程", "开发", "code", "develop", "github"],
    "file": ["文件", "读写", "file", "read", "write"],
    "calendar": ["日历", "日程", "会议", "calendar", "schedule", "meeting"],
    "task": ["任务", "待办", "todo", "task"],
    "knowledge": ["知识", "笔记", "文档", "knowledge", "note", "notion"],
    "database": ["数据库", "database", "sql", "db"],
}


class MCPToolSelector:
    """MCP 工具意图匹配选择器。

    根据用户意图从可用 MCP 工具中选择最匹配的工具。
    支持用户覆盖自动选择结果。

    匹配优先级：
    1. 用户覆盖（最高优先级）
    2. 工具名称精确匹配
    3. 分类关键词匹配
    4. 描述关键词匹配
    5. 标签匹配
    """

    def __init__(self, user_override: dict[str, str] | None = None) -> None:
        """初始化 MCP 工具选择器。

        Args:
            user_override: 用户指定的工具覆盖映射，key 为任务类型，value 为工具名称。
        """
        self._user_override: dict[str, str] = user_override or {}

    def select_tool(
        self,
        intent: str,
        available_tools: list[MCPToolInfo],
        user_override: str | None = None,
    ) -> MCPToolInfo | None:
        """根据意图从可用工具中选择最匹配的 MCP 工具。

        Args:
            intent: 用户意图描述。
            available_tools: 当前可用的 MCP 工具列表。
            user_override: 本次调用指定的工具名称覆盖，优先级最高。

        Returns:
            匹配到的 MCPToolInfo，无匹配时返回 None。
        """
        if not intent or not available_tools:
            logger.debug("select_tool: intent 或 available_tools 为空，跳过匹配")
            return None

        # 0. 用户覆盖 — 本次调用指定
        if user_override:
            tool = self._find_by_name(user_override, available_tools)
            if tool:
                logger.info("用户覆盖选择工具: %s → %s", user_override, tool.tool_name)
                return tool
            logger.warning("用户覆盖的工具未找到: %s", user_override)

        # 0.5 用户覆盖 — 构造时配置
        override_tool_name = self._user_override.get(intent)
        if override_tool_name:
            tool = self._find_by_name(override_tool_name, available_tools)
            if tool:
                logger.info("配置覆盖选择工具: %s → %s", intent, tool.tool_name)
                return tool
            logger.warning("配置覆盖的工具未找到: %s", override_tool_name)

        # 1. 工具名称精确匹配
        tool = self._match_by_name(intent, available_tools)
        if tool:
            logger.info("名称匹配选择工具: intent=%s → %s", intent, tool.tool_name)
            return tool

        # 2. 分类关键词匹配
        tool = self._match_by_category(intent, available_tools)
        if tool:
            logger.info("分类匹配选择工具: intent=%s → %s", intent, tool.tool_name)
            return tool

        # 3. 描述关键词匹配
        tool = self._match_by_description(intent, available_tools)
        if tool:
            logger.info("描述匹配选择工具: intent=%s → %s", intent, tool.tool_name)
            return tool

        # 4. 标签匹配
        tool = self._match_by_tags(intent, available_tools)
        if tool:
            logger.info("标签匹配选择工具: intent=%s → %s", intent, tool.tool_name)
            return tool

        logger.info("未找到匹配的 MCP 工具: intent=%s", intent)
        return None

    # ------------------------------------------------------------------
    # 内部匹配方法
    # ------------------------------------------------------------------

    @staticmethod
    def _find_by_name(name: str, tools: list[MCPToolInfo]) -> MCPToolInfo | None:
        """按工具名称查找（精确匹配，不区分大小写）。"""
        name_lower = name.lower()
        for tool in tools:
            if tool.tool_name.lower() == name_lower and tool.status == "ACTIVE":
                return tool
        return None

    def _match_by_name(self, intent: str, tools: list[MCPToolInfo]) -> MCPToolInfo | None:
        """检查意图是否直接包含工具名称（不区分大小写）。

        当用户意图中明确提到了某个工具的名称时，直接返回该工具。
        """
        intent_lower = intent.lower()
        for tool in tools:
            if tool.status != "ACTIVE":
                continue
            if tool.tool_name.lower() in intent_lower:
                return tool
        return None

    def _match_by_category(self, intent: str, tools: list[MCPToolInfo]) -> MCPToolInfo | None:
        """分类关键词匹配。

        将意图中的关键词映射到工具分类，然后返回该分类下第一个 ACTIVE 工具。
        """
        intent_lower = intent.lower()
        matched_category: str | None = None

        for category, keywords in CATEGORY_KEYWORDS.items():
            for keyword in keywords:
                if keyword.lower() in intent_lower:
                    matched_category = category
                    break
            if matched_category:
                break

        if matched_category is None:
            return None

        # 在匹配到的分类中查找第一个 ACTIVE 工具
        for tool in tools:
            if tool.status != "ACTIVE":
                continue
            # 检查工具名称或描述中是否包含分类关键词
            tool_text = f"{tool.tool_name} {tool.description}".lower()
            category_keywords = CATEGORY_KEYWORDS[matched_category]
            for keyword in category_keywords:
                if keyword.lower() in tool_text:
                    return tool

        return None

    def _match_by_description(self, intent: str, tools: list[MCPToolInfo]) -> MCPToolInfo | None:
        """描述关键词匹配（简单关键词重叠评分）。

        将意图分词后，统计每个工具描述中包含的关键词数量，
        返回得分最高且得分 > 0 的工具。
        """
        intent_words = self._tokenize(intent)
        if not intent_words:
            return None

        best_tool: MCPToolInfo | None = None
        best_score = 0

        for tool in tools:
            if tool.status != "ACTIVE":
                continue
            desc_lower = tool.description.lower()
            score = sum(1 for word in intent_words if word in desc_lower)
            if score > best_score:
                best_score = score
                best_tool = tool

        return best_tool if best_score > 0 else None

    def _match_by_tags(self, intent: str, tools: list[MCPToolInfo]) -> MCPToolInfo | None:
        """标签匹配。

        检查工具的 tags 字段是否与意图关键词匹配。
        返回第一个匹配的工具。
        """
        intent_words = self._tokenize(intent)
        if not intent_words:
            return None

        for tool in tools:
            if tool.status != "ACTIVE":
                continue
            if not tool.tags:
                continue
            tag_lowers = [t.lower() for t in tool.tags]
            for word in intent_words:
                if any(word in tag for tag in tag_lowers):
                    return tool

        return None

    @staticmethod
    def _tokenize(text: str) -> list[str]:
        """将文本分词为小写关键词列表。

        支持中英文混合：
        - 英文：按非字母数字字符分割
        - 中文：按单字分割
        """
        tokens: list[str] = []

        # 提取英文单词
        en_words = re.findall(r"[a-zA-Z0-9]+", text)
        tokens.extend(w.lower() for w in en_words)

        # 提取中文字符（每个字作为一个 token）
        cn_chars = re.findall(r"[\u4e00-\u9fff]", text)
        tokens.extend(cn_chars)

        # 同时提取连续中文子串（2字及以上）作为组合 token
        cn_words = re.findall(r"[\u4e00-\u9fff]{2,}", text)
        tokens.extend(cn_words)

        return tokens


mcp_tool_selector = MCPToolSelector()
