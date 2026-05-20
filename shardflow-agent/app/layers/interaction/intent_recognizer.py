import re

from app.layers.agent_core.llm_router import llm_router
from app.layers.agent_core.prompt_engine import prompt_engine


class IntentRecognizer:
    """Hybrid intent recognition: rules-first with LLM fallback."""

    RULES: dict[str, list[str]] = {
        "code_exploration": [
            "理清", "探索", "分析链路", "梳理", "了解", "查看", "理解",
            "是怎么", "如何工作", "调用链", "调用关系", "架构",
        ],
        "code_fix": [
            "修复", "fix", "bug", "报错", "错误", "异常", "崩溃",
            "修好", "改好", "解决.*问题",
        ],
        "design_proposal": [
            "设计", "方案", "架构", "重构", "选型", "技术方案",
            "怎么实现", "如何设计",
        ],
        "doc_generation": [
            "生成文档", "写注释", "接口文档", "api文档", "readme",
            "文档", "注释",
        ],
    }

    RULE_CONFIDENCE_THRESHOLD: float = 0.40

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
        confidence = min(scores[best] * 0.45, 1.0)
        return best, confidence

    async def _llm_classify(self, user_input: str) -> tuple[str, float]:
        prompt = prompt_engine.build_intent_classify_prompt(user_input)
        try:
            model = llm_router.select_model("intent_recognition")
            response = await llm_router.call_with_retry(prompt, model)
            content = await llm_router.extract_content(response)
            intent = content.strip().lower()
            valid_intents = {
                "code_exploration", "code_fix", "design_proposal",
                "doc_generation", "general_qa",
            }
            if intent not in valid_intents:
                intent = "general_qa"
            return intent, 0.6
        except Exception:
            return "general_qa", 0.3


intent_recognizer = IntentRecognizer()
