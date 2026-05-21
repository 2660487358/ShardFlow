from typing import Any


class PromptEngine:
    """Manages prompt templates and dynamic assembly for ReAct loop stages."""

    TEMPLATES: dict[str, str] = {
        "system_think": (
            "你是一个代码分析 Agent，正在执行以下任务：\n\n"
            "【任务目标】\n{task_goal}\n\n"
            "【已知上下文】\n{context_shard_info}\n\n"
            "【当前进度】\n已完成 {completed_steps} 步，共 {total_estimated_steps} 步\n\n"
            "【上一步观察】\n{last_observation}\n\n"
            "请思考下一步应该执行什么操作。你可以：\n"
            "1. 调用工具获取更多信息\n"
            "2. 基于已有信息得出结论\n"
            "3. 如果信息已足够，输出最终答案"
        ),
        "system_observe": (
            "你是一个代码分析 Agent。以下是工具执行的结果：\n\n"
            "【工具】{tool_name}\n"
            "【参数】{tool_params}\n"
            "【执行结果】\n{execution_result}\n\n"
            "请分析这个结果，更新你对当前任务的理解。"
        ),
        "intent_classify": (
            "请将以下用户输入分类为以下意图之一：\n"
            "- code_exploration: 探索代码/理清链路/分析流程\n"
            "- code_fix: 修复Bug/解决报错\n"
            "- design_proposal: 设计方案/架构/重构\n"
            "- doc_generation: 生成文档/写注释\n"
            "- general_qa: 通用问答\n\n"
            "用户输入：{user_input}\n\n"
            "只返回意图类型，不要其他内容。"
        ),
        "shard_extract": (
            "基于以下对话历史，提取结构化的状态包信息。\n\n"
            "【对话历史】\n{conversation_history}\n\n"
            "【已有状态包】\n{existing_shard}\n\n"
            '请以 JSON 格式输出，包含字段：confirmed（已确认知识点列表）、excluded（已排除假设列表）、'
            "pending（待探索问题列表）、key_decisions（关键决策列表）。\n"
            "每个 confirmed 项需包含 fact、confidence、evidence。\n"
            "每个 excluded 项需包含 hypothesis、reason。\n"
            "每个 key_decision 项需包含 decision、reason、confidence。"
        ),
        "summarize": (
            "请将以下对话历史压缩为简洁的摘要，保留关键事实、决策和待解决问题：\n\n"
            "{conversation_history}\n\n"
            "摘要："
        ),
    }

    def load_template(self, name: str) -> str:
        template = self.TEMPLATES.get(name)
        if template is None:
            raise ValueError(f"Unknown template: {name}")
        return template

    def assemble_prompt(self, template: str, variables: dict[str, Any]) -> str:
        return template.format(**variables)

    def build_think_prompt(self, state: dict[str, Any]) -> str:
        task_goal = state.get("user_input", "")
        context_shard_info = state.get("context_shard_info", "无（首次探索）")
        completed_steps = state.get("loop_count", 0)
        total_estimated_steps = state.get("max_rounds", 15)
        last_observation = state.get("observation", "无（开始推理）")

        template = self.load_template("system_think")
        return self.assemble_prompt(template, {
            "task_goal": task_goal,
            "context_shard_info": context_shard_info,
            "completed_steps": completed_steps,
            "total_estimated_steps": total_estimated_steps,
            "last_observation": last_observation,
        })

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
