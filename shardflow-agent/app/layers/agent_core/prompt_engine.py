from typing import Any


class PromptEngine:
    """Manages prompt templates and dynamic assembly for ReAct loop stages.

    个人助手版：系统人设为"ShardFlow个人智能助手"，支持画像注入、工具动态生成、意图路由。
    """

    # ---- 核心模板 ----

    TEMPLATES: dict[str, str] = {
        # 系统思考模板（个人助手人设）
        "system_think": (
            "你是 ShardFlow 个人智能助手，正在帮助用户完成以下任务。\n\n"
            "【用户画像】\n{profile_context}\n\n"
            "【任务目标】\n{task_goal}\n\n"
            "【任务类型】{task_type}\n\n"
            "【已知上下文】\n{context_shard_info}\n\n"
            "【当前进度】\n"
            "已完成 {completed_steps} 步，共约 {total_estimated_steps} 步\n"
            "执行状态: {execution_summary}\n\n"
            "【上一步观察】\n{last_observation}\n\n"
            "【可用工具列表】\n{tool_list}\n\n"
            "请思考下一步应该执行什么操作。你可以：\n"
            "1. 调用工具获取更多信息\n"
            "2. 基于已有信息得出结论\n"
            "3. 如果信息已足够，输出最终答案\n\n"
            "【输出格式要求】\n"
            "请先输出你的思考过程（纯文本），然后在最后输出一个 JSON 块表示你的行动决策。\n"
            "如果需要调用工具，JSON 格式如下：\n"
            '```json\n{{"action_plan": {{"tool": "工具名", "params": {{参数键值对}}, "source_type": "来源类型"}}}}\n```\n'
            "如果已有足够信息可以输出最终答案，JSON 格式如下：\n"
            '```json\n{{"final_answer": "你的最终答案内容", "is_done": true}}\n```\n'
            "注意：JSON 块必须用 ```json 和 ``` 包裹，确保可以被正确解析。"
        ),

        "system_observe": (
            "你是 ShardFlow 个人智能助手。以下是工具执行的结果：\n\n"
            "【工具】{tool_name}\n"
            "【参数】{tool_params}\n"
            "【执行结果】\n{execution_result}\n\n"
            "请分析这个结果，更新你对当前任务的理解。"
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

        # 状态包提取模板
        "shard_extract": (
            "基于以下对话历史，提取结构化的状态包信息。\n\n"
            "【对话历史】\n{conversation_history}\n\n"
            "【已有状态包】\n{existing_shard}\n\n"
            '请以 JSON 格式输出，包含字段：\n'
            "- confirmed: 已确认知识点列表（每个含 fact/confidence/evidence）\n"
            "- excluded: 已排除假设列表（每个含 hypothesis/reason）\n"
            "- pending: 待探索问题列表（字符串数组）\n"
            "- key_decisions: 关键决策列表（每个含 decision/reason/confidence）\n"
            "- task_type: 任务类型\n"
            "- task_goal: 任务目标摘要\n"
        ),

        # 摘要模板
        "summarize": (
            "请将以下对话历史压缩为简洁的摘要，保留关键事实、决策和待解决问题：\n\n"
            "{conversation_history}\n\n"
            "摘要："
        ),

        # 画像注入模板
        "profile_inject": (
            "【用户画像已应用】\n"
            "专业水平: {expertise_level}\n"
            "回答深度偏好: {preferred_depth}\n"
            "沟通风格: {communication_style}\n"
            "专注领域: {domains}\n"
            "技术栈: {tech_stack}\n"
            "信息来源偏好: {preferred_sources}\n"
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

    # ---- Profile Injection ----

    def build_profile_inject_prompt(self, profile: dict[str, Any]) -> str:
        """生成画像注入提示文本。"""
        template = self.load_template("profile_inject")
        return self.assemble_prompt(template, {
            "expertise_level": profile.get("expertise_level", "intermediate"),
            "preferred_depth": profile.get("preferred_depth", "DETAIL"),
            "communication_style": profile.get("communication_style", "concise"),
            "domains": ", ".join(profile.get("domains", [])) or "通用",
            "tech_stack": ", ".join(profile.get("tech_stack", [])) or "通用",
            "preferred_sources": ", ".join(
                f"{k}({v:.0%})" for k, v in profile.get("preferred_sources", {}).items()
            ) or "默认",
        })

    # ---- Dynamic Tool List ----

    def _build_tool_list(self) -> str:
        """从 ToolRegistry 动态生成工具列表文本。"""
        try:
            from app.layers.tool.tool_registry import tool_registry
            tools = tool_registry.list_all()
            if tools:
                lines = []
                for t in tools:
                    lines.append(f"- {t.name}: {t.description}")
                return "\n".join(lines)
        except Exception:
            pass
        # Fallback: 硬编码的基本工具列表
        return (
            "- web_search: 联网搜索，参数: query(搜索关键词)\n"
            "- read_file: 读取指定文件内容，参数: path(文件路径)\n"
            "- write_file: 写入文件，参数: path(文件路径), content(内容)\n"
            "- code_analyze: 代码分析，参数: path(文件路径), query(分析问题)\n"
            "- extract_shard: 提取状态包快照，参数: scope(提取范围)\n"
            "- query_strategy: 查询历史策略，参数: intent(意图类型), query(查询内容)\n"
            "- save_strategy: 保存当前策略，参数: strategy(策略内容)"
        )

    # ---- Build Methods ----

    def build_think_prompt(self, state: dict[str, Any]) -> str:
        task_goal = state.get("user_input", "")
        task_type = state.get("intent", "general_qa")
        context_shard_info = state.get("context_shard_info", "无（首次对话）")
        completed_steps = state.get("loop_count", 0)
        total_estimated_steps = state.get("max_rounds", 15)
        last_observation = state.get("observation", "无（开始推理）")

        # 画像上下文
        profile_context = state.get("profile_context", "暂无用户画像")

        # 执行状态摘要
        exec_state = state.get("execution_state") or {}
        tools_used = exec_state.get("tools_used", [])
        execution_summary = f"已使用工具: {', '.join(tools_used)}" if tools_used else "尚未使用工具"

        # 意图提示
        intent_hint = self.INTENT_PROMPT_HINTS.get(task_type, "")

        template = self.load_template("system_think")
        base = self.assemble_prompt(template, {
            "profile_context": profile_context,
            "task_goal": task_goal,
            "task_type": task_type,
            "context_shard_info": context_shard_info,
            "completed_steps": completed_steps,
            "total_estimated_steps": total_estimated_steps,
            "execution_summary": execution_summary,
            "last_observation": last_observation,
            "tool_list": self._build_tool_list(),
        })

        if intent_hint:
            base += f"\n\n【特别提示】{intent_hint}"

        return base

    def build_observe_prompt(self, state: dict[str, Any]) -> str:
        action_plan = state.get("action_plan") or {}
        tool_name = action_plan.get("tool", "unknown")
        tool_params = action_plan.get("params", {})
        execution_result = state.get("observation") or "无结果"

        template = self.load_template("system_observe")
        return self.assemble_prompt(template, {
            "tool_name": tool_name,
            "tool_params": tool_params,
            "execution_result": execution_result,
        })

    def build_intent_classify_prompt(self, user_input: str) -> str:
        template = self.load_template("intent_classify")
        return self.assemble_prompt(template, {"user_input": user_input})

    def build_shard_extract_prompt(self, conversation_history: str, existing_shard: str = "无") -> str:
        template = self.load_template("shard_extract")
        return self.assemble_prompt(template, {
            "conversation_history": conversation_history,
            "existing_shard": existing_shard,
        })

    def build_summarize_prompt(self, conversation_history: str) -> str:
        template = self.load_template("summarize")
        return self.assemble_prompt(template, {"conversation_history": conversation_history})


prompt_engine = PromptEngine()
