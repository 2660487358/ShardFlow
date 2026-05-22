import re

from app.layers.agent_core.llm_router import llm_router
from app.layers.agent_core.prompt_engine import prompt_engine


class IntentRecognizer:
    """Hybrid intent recognition: rules-first with LLM fallback.

    15+ 通用意图体系，覆盖个人助手多元任务场景：
    - 知识获取: research, web_search, knowledge_qa
    - 文档写作: write_doc, write_code
    - 任务管理: task_plan, schedule, file_op
    - 代码相关: code_explore, code_fix, design_proposal
    - 交互协作: continue_task, feedback, message_send
    - 系统通知: notification
    - 兜底: general_qa
    """

    RULES: dict[str, list[str]] = {
        # ---- 知识获取 ----
        "research": [
            "调研", "研究", "分析", "对比", "选型", "评估",
            "优缺点", "最佳实践", "技术方案", "综述", "梳理",
            "了解", "介绍一下", "什么是", "如何理解",
        ],
        "web_search": [
            "搜索", "查一下", "查查", "搜索一下", "帮我找",
            "有没有", "最新", "新闻", "趋势", "动态",
        ],
        "knowledge_qa": [
            "是什么", "为什么", "怎么理解", "解释一下",
            "区别", "概念", "定义", "含义", "原理",
        ],

        # ---- 文档写作 ----
        "write_doc": [
            "写文档", "生成文档", "写报告", "写总结", "写纪要",
            "会议记录", "整理笔记", "写周报", "写日报", "写方案",
            "文档", "readme", "api文档", "接口文档",
        ],
        "write_code": [
            "写代码", "生成代码", "实现", "编写", "开发",
            "写一个", "创建一个", "添加功能", "新增接口",
        ],

        # ---- 任务管理 ----
        "task_plan": [
            "计划", "规划", "安排", "方案", "步骤", "流程",
            "怎么做", "如何处理", "如何实现", "如何设计",
        ],
        "schedule": [
            "日程", "日历", "提醒", "定时", "预约", "会议",
            "几点", "什么时候", "安排时间", "设置提醒",
        ],
        "file_op": [
            "读文件", "打开文件", "查看文件", "列出目录",
            "文件内容", "读取", "保存文件", "写入文件",
        ],

        # ---- 代码相关 ----
        "code_explore": [
            "理清", "探索", "分析链路", "调用链", "调用关系",
            "架构", "依赖", "代码结构", "模块", "入口",
        ],
        "code_fix": [
            "修复", "fix", "bug", "报错", "错误", "异常",
            "崩溃", "修好", "改好", "解决.*问题", "debug",
        ],
        "design_proposal": [
            "设计方案", "架构设计", "重构方案", "技术选型",
            "系统设计", "接口设计", "数据库设计",
        ],

        # ---- 交互协作 ----
        "continue_task": [
            "继续", "接着", "上次", "续接", "恢复", "回到",
            "之前的任务", "之前的对话", "回到刚才",
        ],
        "feedback": [
            "反馈", "评价", "建议", "意见", "好不好",
            "怎么样", "有用吗", "评分",
        ],
        "message_send": [
            "发送消息", "发消息", "通知", "告诉", "转达",
            "发给", "发送给",
        ],
    }

    RULE_CONFIDENCE_THRESHOLD: float = 0.35

    # 有效的 LLM 分类意图列表
    VALID_INTENTS: set[str] = {
        "research", "web_search", "knowledge_qa",
        "write_doc", "write_code",
        "task_plan", "schedule", "file_op",
        "code_explore", "code_fix", "design_proposal",
        "continue_task", "feedback", "message_send",
        "notification", "general_qa",
    }

    # 意图 → 策略路由映射
    INTENT_STRATEGY_MAP: dict[str, str] = {
        "research": "technology_research",
        "web_search": "web_search",
        "knowledge_qa": "knowledge_qa",
        "write_doc": "doc_writing",
        "write_code": "code_generation",
        "task_plan": "task_planning",
        "schedule": "schedule_management",
        "file_op": "file_management",
        "code_explore": "general_code_exploration",
        "code_fix": "error_troubleshooting",
        "design_proposal": "architecture_design",
        "continue_task": "session_resume",
        "feedback": "user_feedback",
        "message_send": "communication",
        "notification": "notification",
        "general_qa": "general_qa",
    }

    def recognize(self, user_input: str) -> tuple[str, float]:
        intent, confidence = self._rule_match(user_input)
        if intent is not None and confidence > self.RULE_CONFIDENCE_THRESHOLD:
            return intent, confidence
        return "general_qa", 0.5

    async def recognize_async(self, user_input: str) -> tuple[str, float]:
        intent, confidence = self._rule_match(user_input)
        if intent is not None and confidence > self.RULE_CONFIDENCE_THRESHOLD:
            return intent, confidence
        return await self._llm_classify(user_input)

    def get_strategy_name(self, intent: str) -> str:
        """将意图映射到对应策略名称。"""
        return self.INTENT_STRATEGY_MAP.get(intent, "general_qa")

    def _rule_match(self, user_input: str) -> tuple[str | None, float]:
        scores: dict[str, float] = {}
        for intent, patterns in self.RULES.items():
            match_count = 0.0
            for pattern in patterns:
                if re.search(pattern, user_input, re.IGNORECASE):
                    match_count += 1.0
            if match_count > 0:
                scores[intent] = match_count

        if not scores:
            return None, 0.0

        best = max(scores, key=lambda k: scores[k])
        confidence = min(scores[best] * 0.40, 1.0)
        return best, confidence

    async def _llm_classify(self, user_input: str) -> tuple[str, float]:
        prompt = prompt_engine.build_intent_classify_prompt(user_input)
        try:
            model = llm_router.select_model("intent_recognition")
            response = await llm_router.call_with_retry(prompt, model)
            content = await llm_router.extract_content(response)
            intent = content.strip().lower()
            if intent not in self.VALID_INTENTS:
                intent = "general_qa"
            return intent, 0.6
        except Exception:
            return "general_qa", 0.3


intent_recognizer = IntentRecognizer()
