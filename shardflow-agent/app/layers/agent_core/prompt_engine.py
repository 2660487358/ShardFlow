import hashlib
import time
import logging
from typing import Any

logger = logging.getLogger(__name__)


class PromptEngine:
    """Manages prompt templates and dynamic assembly for ReAct loop stages.

    个人助手版：系统人设为"ShardFlow个人智能助手"，支持工具动态生成、意图路由。

    性能优化：系统模板和工具列表（静态内容）做 hash 缓存，避免每次请求重复构建。
    缓存 key = hash(模板名 + 工具列表)，命中时直接复用缓存字符串，Prefill 阶段可受益于
    OpenAI/Anthropic Prompt Caching（静态前缀的 KV Cache 跨请求复用）。
    """

    def __init__(self) -> None:
        # Cache: {hash_key: (cached_text, timestamp)}
        self._static_cache: dict[str, tuple[str, float]] = {}
        # 缓存过期时间（秒）：工具列表可能动态更新，5 分钟后失效
        self._cache_ttl: float = 300.0

    # ---- 核心模板 ----

    TEMPLATES: dict[str, str] = {
        # 系统思考模板（个人助手人设 — 输出行为规范版）
        "system_think": (
            "你是 ShardFlow 个人智能助手，正在帮助用户完成以下任务。\n\n"
            "【任务目标】\n{task_goal}\n\n"
            "【任务类型】{task_type}\n\n"
            "【当前进度】\n"
            "已完成 {completed_steps} 步，共约 {total_estimated_steps} 步\n"
            "执行状态: {execution_summary}\n\n"
            "【上一步观察】\n{last_observation}\n\n"
            "【可用工具列表】\n{tool_list}\n\n"
            "请思考下一步应该执行什么操作。你可以：\n"
            "1. 调用工具获取更多信息\n"
            "2. 基于已有信息得出结论\n"
            "3. 如果信息已足够，输出最终答案\n\n"

            "【输出结构约束（强制执行）】\n"
            "你的响应必须严格遵循以下结构，禁止输出任何其他内容：\n"
            "<THINKING>\n"
            "[此处填写你的内部思考过程，用户不可见]\n"
            "</THINKING>\n\n"
            "<ANSWER>\n"
            "[此处填写面向用户的最终答案，仅此处内容对用户可见]\n"
            "</ANSWER>\n\n"

            "【THINKING 标签规则】\n"
            "- 仅用于记录你的推理过程、分析步骤、决策依据\n"
            '- 禁止包含自我指涉的元评论（如"让我搜索一下"、"我需要调研"、"基于当前状态"）\n'
            '- 禁止包含"我需要提供"、"我应该"、"我可以基于"等自我指涉表述\n'
            '- 禁止包含"无需调用工具"、"可以直接基于知识"等工具调用决策暴露\n'
            '- 禁止包含"这是一个开放式的讨论话题"等对用户意图的元评论\n'
            "- 正确示例：'RPC框架的核心是远程调用透明化，需要关注序列化、网络传输、服务发现三个维度'\n"
            "- 错误示例：'我需要提供一个全面但不过于基础的介绍，无需调用工具'\n"
            "- 如果不需要思考，此标签可为空，但标签本身必须保留\n\n"

            "【ANSWER 标签规则】\n"
            "- 必须直接回应用户问题，首句直接回答，禁止铺垫性语句\n"
            "- 禁止引用 THINKING 中的任何内容\n"
            '- 禁止包含"让我想想"、"我需要"、"基于当前状态"、"我刚刚搜索了"等元评论\n'
            "- 禁止暴露内部工具名称、调用次数、执行状态\n"
            "- 禁止包含未经验证的信息来源（除非明确标注）\n"
            "- 必须使用标准 Markdown 格式\n\n"

            "【工具调用规范】\n"
            "当你需要调用工具时，在 <THINKING> 内以自然语言描述调用意图，\n"
            "然后在 <ANSWER> 中输出以下 JSON 块（这是唯一允许在 ANSWER 中出现 JSON 的场景）：\n"
            '```json\n{{"action_plan": {{"tool": "工具名", "params": {{参数键值对}}, "source_type": "来源类型"}}}}\n```\n'
            "如果已有足够信息可以输出最终答案，在 <ANSWER> 中直接输出自然语言答案，不包含任何 JSON：\n"
            "<ANSWER>\n"
            "你的最终答案内容（纯 Markdown）\n"
            "</ANSWER>\n\n"

            "【禁止行为（零容忍）】\n"
            "- 禁止在 <ANSWER> 中输出 <THINKING> 的内容\n"
            '- 禁止在 <ANSWER> 中使用"让我想想"、"我需要"、"基于当前状态"等元评论\n'
            "- 禁止在 <ANSWER> 中暴露内部工具名称、调用次数、执行耗时\n"
            '- 禁止在 <ANSWER> 中描述"我刚刚搜索了"、"根据搜索结果"等过程性表述\n'
            "- 禁止在 <ANSWER> 中输出未转义的 JSON（工具调用 JSON 块除外）\n\n"

            "【Markdown 格式规范】\n"
            "- 表格必须每行独占一行，禁止将多行表格挤在同一行\n"
            "- 正确示例：\n"
            "| 方案 | 特点 | 适用场景 |\n"
            "|:-----|:-----|:---------|\n"
            "| Protobuf | 平衡性好 | 通用推荐 |\n\n"
            "- 错误示例（禁止）：| 方案 | 特点 | 适用场景 | |------|------|----------| | Protobuf | 平衡性好 | 通用推荐 |\n"
            "- 表格列之间用空格分隔，表头与分隔行之间必须换行\n\n"

            "【表格输出规范（强制执行）】\n"
            "1. 表格前必须有1-2句上下文说明，禁止直接输出裸表\n"
            "   ✅ 正确：'以下是 gRPC 与 Thrift 在核心设计上的对比：'\n"
            "   ❌ 禁止：直接输出 | 维度 | A | B |\n"
            "2. 分隔行必须包含对齐标记：:---（左对齐）、---:（右对齐）、:---:（居中）\n"
            "   ✅ 正确：|:-----|:-----:|---:|\n"
            "   ❌ 禁止：|------|------|------|\n"
            "3. 对比类表格第一列为对比维度（左对齐），后续列为对比对象\n"
            "4. 单个单元格内容不超过30个汉字，超长内容提炼关键词，详细说明放表格后\n"
            "5. 禁止在单元格内嵌套无序列表（- item），如需分段用<br>\n"
            "6. 表格后必须有1-3句关键差异解读或结论，禁止表格后直接结束\n"
            "7. 列数超过5列时必须拆分为多个子表格分组对比\n"
            "8. 每个维度名称不超过8个字\n"
        ),

        "system_observe": (
            "你是 ShardFlow 个人智能助手。以下是工具执行的结果：\n\n"
            "【执行结果】\n{execution_result}\n\n"
            "请分析这个结果，更新你对当前任务的理解。\n\n"
            "【输出结构约束（强制执行）】\n"
            "你的响应必须严格遵循以下结构：\n"
            "<THINKING>\n"
            "[内部思考过程]\n"
            "</THINKING>\n\n"
            "<ANSWER>\n"
            "[下一步决策的 JSON 或继续推理的自然语言]\n"
            "</ANSWER>\n\n"
            "注意：不要在输出中重复工具名称或调用参数，只需分析结果本身。\n"
        ),

        # 意图分类提示（15+ 意图）
        "intent_classify": (
            "请将以下用户输入分类为以下意图之一：\n"
            "- research: 调研/研究/分析/对比/选型\n"
            "- web_search: 搜索/查找最新信息\n"
            "- knowledge_qa: 知识问答/概念解释\n"
            "- write_doc: 写文档/报告/纪要/总结\n"
            "- write_code: 写代码/生成代码/实现功能\n"
            "- task_plan: 制定计划/规划方案\n"
            "- schedule: 日程管理/日历/提醒\n"
            "- file_op: 文件操作/读取/写入\n"
            "- code_explore: 探索代码/理清链路\n"
            "- code_fix: 修复Bug/解决报错\n"
            "- design_proposal: 设计方案/架构设计\n"
            "- continue_task: 继续之前的任务\n"
            "- feedback: 反馈/评价/建议\n"
            "- message_send: 发送消息/通知他人\n"
            "- notification: 系统通知\n"
            "- general_qa: 通用问答（兜底）\n\n"
            "用户输入：{user_input}\n\n"
            "只返回意图类型（小写英文），不要其他内容。"
        ),

        # 摘要模板
        "summarize": (
            "请将以下对话历史压缩为简洁的摘要，保留关键事实、决策和待解决问题：\n\n"
            "{conversation_history}\n\n"
            "摘要："
        ),

    }

    # ---- 意图 → Prompt 变体选择 ----
    INTENT_PROMPT_HINTS: dict[str, str] = {
        "research": "请进行深入调研，对比分析不同方案，给出有依据的建议。",
        "web_search": "请优先使用搜索工具获取最新信息。",
        "knowledge_qa": "请用清晰易懂的方式解释概念，适当举例说明。",
        "write_doc": "请生成结构清晰、格式规范的文档。",
        "write_code": "请生成可运行的代码，包含必要的注释和错误处理。",
        "task_plan": "请制定分步骤的执行计划，明确各阶段的交付物。",
        "schedule": "请帮助管理日程，注意时间冲突和优先级。",
        "file_op": "请准确执行文件操作，注意路径安全。",
        "code_explore": "请系统性地分析代码结构和调用关系。",
        "code_fix": "请定位问题根因，给出修复方案和验证步骤。",
        "design_proposal": "请给出完整的架构设计方案，包含组件图和数据流。",
        "continue_task": "请先恢复上次任务的上下文，然后继续执行。",
        "feedback": "请收集和整理用户反馈。",
        "message_send": "请帮助编辑和发送消息。",
        "notification": "请检查和处理系统通知。",
        "general_qa": "请全面、准确地回答用户的问题。",
    }

    def load_template(self, name: str) -> str:
        template = self.TEMPLATES.get(name)
        if template is None:
            raise ValueError(f"Unknown template: {name}")
        return template

    def assemble_prompt(self, template: str, variables: dict[str, Any]) -> str:
        return template.format(**variables)

    # ---- Dynamic Tool List ----

    def _build_tool_list(self) -> str:
        """从 ToolRegistry 动态生成工具列表文本。结果带缓存，5 分钟后刷新。"""
        cache_key = "tool_list_v2"
        cached = self._static_cache.get(cache_key)
        if cached:
            cached_text, ts = cached
            if time.time() - ts < self._cache_ttl:
                return cached_text

        try:
            from app.layers.tool.tool_registry import tool_registry
            tools = tool_registry.list_all()
            if tools:
                lines = []
                for t in tools:
                    lines.append(f"- {t.tool_name}: {t.description}")
                result = "\n".join(lines)
                self._static_cache[cache_key] = (result, time.time())
                return result
        except Exception:
            pass
        # Fallback: 硬编码的基本工具列表
        result = (
            "- web_search: 联网搜索，参数: query(搜索关键词)\n"
            "- read_file: 读取指定文件内容，参数: path(文件路径)\n"
            "- write_file: 写入文件，参数: path(文件路径), content(内容)\n"
            "- code_analyze: 代码分析，参数: path(文件路径), query(分析问题)\n"
        )
        self._static_cache[cache_key] = (result, time.time())
        return result

    def _build_static_think_prefix(self) -> str:
        """构建 think prompt 中不变的静态前缀。

        包括：系统人设、角色定义、输出结构约束、工具列表。
        这些内容在多次请求间完全相同，作为 prompt 前缀放置在最前面，
        可利用服务端的 Prompt Caching 机制复用 KV Cache。

        Returns:
            (static_prefix, static_hash) — hash 用于标记缓存版本
        """
        tool_list = self._build_tool_list()
        # 静态前缀：角色 + 输出结构约束 + 工具列表
        static_prefix = (
            "你是 ShardFlow 个人智能助手，正在帮助用户完成以下任务。\n\n"
            "【可用工具列表】\n{tool_list}\n\n"
            "请思考下一步应该执行什么操作。你可以：\n"
            "1. 调用工具获取更多信息\n"
            "2. 基于已有信息得出结论\n"
            "3. 如果信息已足够，输出最终答案\n\n"

            "【输出结构约束（强制执行）】\n"
            "你的响应必须严格遵循以下结构，禁止输出任何其他内容：\n"
            "<THINKING>\n"
            "[此处填写你的内部思考过程，用户不可见]\n"
            "</THINKING>\n\n"
            "<ANSWER>\n"
            "[此处填写面向用户的最终答案，仅此处内容对用户可见]\n"
            "</ANSWER>\n\n"

            "【THINKING 标签规则】\n"
            "- 仅用于记录你的推理过程、分析步骤、决策依据\n"
            '- 禁止包含自我指涉的元评论（如"让我搜索一下"、"我需要调研"、"基于当前状态"）\n'
            '- 禁止包含"我需要提供"、"我应该"、"我可以基于"等自我指涉表述\n'
            '- 禁止包含"无需调用工具"、"可以直接基于知识"等工具调用决策暴露\n'
            '- 禁止包含"这是一个开放式的讨论话题"等对用户意图的元评论\n'
            "- 正确示例：'RPC框架的核心是远程调用透明化，需要关注序列化、网络传输、服务发现三个维度'\n"
            "- 错误示例：'我需要提供一个全面但不过于基础的介绍，无需调用工具'\n"
            "- 如果不需要思考，此标签可为空，但标签本身必须保留\n\n"

            "【ANSWER 标签规则】\n"
            "- 必须直接回应用户问题，首句直接回答，禁止铺垫性语句\n"
            "- 禁止引用 THINKING 中的任何内容\n"
            '- 禁止包含"让我想想"、"我需要"、"基于当前状态"、"我刚刚搜索了"等元评论\n'
            "- 禁止暴露内部工具名称、调用次数、执行状态\n"
            "- 禁止包含未经验证的信息来源（除非明确标注）\n"
            "- 必须使用标准 Markdown 格式\n\n"

            "【工具调用规范】\n"
            "当你需要调用工具时，在 <THINKING> 内以自然语言描述调用意图，\n"
            "然后在 <ANSWER> 中输出以下 JSON 块（这是唯一允许在 ANSWER 中出现 JSON 的场景）：\n"
            '```json\n{{"action_plan": {{"tool": "工具名", "params": {{参数键值对}}, "source_type": "来源类型"}}}}\n```\n'
            "如果已有足够信息可以输出最终答案，在 <ANSWER> 中直接输出自然语言答案，不包含任何 JSON。\n\n"

            "【禁止行为（零容忍）】\n"
            "- 禁止在 <ANSWER> 中输出 <THINKING> 的内容\n"
            '- 禁止在 <ANSWER> 中使用"让我想想"、"我需要"、"基于当前状态"等元评论\n'
            "- 禁止在 <ANSWER> 中暴露内部工具名称、调用次数、执行耗时\n"
            '- 禁止在 <ANSWER> 中描述"我刚刚搜索了"、"根据搜索结果"等过程性表述\n'
            "- 禁止在 <ANSWER> 中输出未转义的 JSON（工具调用 JSON 块除外）\n\n"

            "【Markdown 格式规范】\n"
            "- 表格必须每行独占一行，禁止将多行表格挤在同一行\n"
            "- 正确示例：\n"
            "| 方案 | 特点 | 适用场景 |\n"
            "|:-----|:-----|:---------|\n"
            "| Protobuf | 平衡性好 | 通用推荐 |\n\n"
            "- 错误示例（禁止）：| 方案 | 特点 | 适用场景 | |------|------|----------| | Protobuf | 平衡性好 | 通用推荐 |\n"
            "- 表格列之间用空格分隔，表头与分隔行之间必须换行\n\n"

            "【表格输出规范（强制执行）】\n"
            "1. 表格前必须有1-2句上下文说明，禁止直接输出裸表\n"
            "   ✅ 正确：'以下是 gRPC 与 Thrift 在核心设计上的对比：'\n"
            "   ❌ 禁止：直接输出 | 维度 | A | B |\n"
            "2. 分隔行必须包含对齐标记：:---（左对齐）、---:（右对齐）、:---:（居中）\n"
            "   ✅ 正确：|:-----|:-----:|---:|\n"
            "   ❌ 禁止：|------|------|------|\n"
            "3. 对比类表格第一列为对比维度（左对齐），后续列为对比对象\n"
            "4. 单个单元格内容不超过30个汉字，超长内容提炼关键词，详细说明放表格后\n"
            "5. 禁止在单元格内嵌套无序列表（- item），如需分段用<br>\n"
            "6. 表格后必须有1-3句关键差异解读或结论，禁止表格后直接结束\n"
            "7. 列数超过5列时必须拆分为多个子表格分组对比\n"
            "8. 每个维度名称不超过8个字\n"
        ).format(tool_list=tool_list)

        prefix_hash = hashlib.md5(static_prefix.encode()).hexdigest()[:12]
        return static_prefix, prefix_hash

    # ---- Build Methods ----

    def build_think_prompt(self, state: dict[str, Any]) -> str:
        """构建 think prompt，动静分离以利用 Prompt Caching。

        静态部分（角色定义 + 工具列表 + 格式要求）在每个请求中相同，
        放在 prompt 最前面，让 OpenAI/Anthropic 的 Prompt Caching 复用 KV Cache。
        动态部分（用户画像、任务目标、上下文、观察）拼接在静态部分之后。
        """
        task_goal = state.get("user_input", "")
        task_type = state.get("intent", "general_qa")
        context_shard_info = state.get("context_shard_info", "无（首次对话）")
        completed_steps = state.get("loop_count", 0)
        total_estimated_steps = state.get("max_rounds", 15)
        last_observation = state.get("observation", "无（开始推理）")

        # 执行状态摘要
        exec_state = state.get("execution_state") or {}
        tools_used = exec_state.get("tools_used", [])
        execution_summary = f"已使用工具: {', '.join(tools_used)}" if tools_used else "尚未使用工具"

        # 意图提示
        intent_hint = self.INTENT_PROMPT_HINTS.get(task_type, "")

        # 知识库检索上下文
        kb_context = state.get("kb_context", "")

        # === 静态前缀（可被服务端 Prompt Caching 缓存）===
        static_prefix, _ = self._build_static_think_prefix()

        # === 动态部分 ===
        dynamic_part = (
            f"\n\n【任务目标】\n{task_goal}\n\n"
            f"【任务类型】{task_type}\n\n"
            f"【已知上下文】\n{context_shard_info}\n\n"
            f"【当前进度】\n"
            f"已完成 {completed_steps} 步，共约 {total_estimated_steps} 步\n"
            f"执行状态: {execution_summary}\n\n"
            f"【上一步观察】\n{last_observation}\n\n"
        )
        if intent_hint:
            dynamic_part += f"【特别提示】{intent_hint}\n"
        if kb_context:
            dynamic_part += f"【知识库检索结果】\n以下是从用户知识库中检索到的相关内容，请优先参考：\n{kb_context}\n\n"

        return static_prefix + dynamic_part

    def build_observe_prompt(self, state: dict[str, Any]) -> str:
        execution_result = state.get("observation") or "无结果"

        template = self.load_template("system_observe")
        return self.assemble_prompt(template, {
            "execution_result": execution_result,
        })

    def build_intent_classify_prompt(self, user_input: str) -> str:
        template = self.load_template("intent_classify")
        return self.assemble_prompt(template, {"user_input": user_input})

    def build_summarize_prompt(self, conversation_history: str) -> str:
        template = self.load_template("summarize")
        return self.assemble_prompt(template, {"conversation_history": conversation_history})


prompt_engine = PromptEngine()
