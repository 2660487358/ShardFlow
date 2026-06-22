"""L2 Agent Core: SkillSelector — LLM 决策模块。

Per Skills管理需求规格文档 FR-7.3 / 实施计划 P5.1.3.

独立封装 LLM 决策逻辑，便于：
- 单元测试（mock LLM 调用）
- 复用（其他场景需要 Skill 选择时可直接调用）
- 替换（V2 阶段可替换为更复杂的决策模型）

与 skill_loader.py 的 _llm_decide 方法互补：
- skill_loader 内部调用 LLMRouter
- skill_selector 提供更丰富的决策策略（如多轮决策、置信度过滤）
"""
from __future__ import annotations

import json
import logging
from typing import Any

from app.models.skill import LoadCandidate, LoadDecision, SkillMeta

logger = logging.getLogger(__name__)


class SkillSelector:
    """LLM 决策模块。

    策略：
    1. 默认：注入 Top-K 元数据，LLM 输出结构化 JSON
    2. 降级：LLM 不可用时，按 final_score 取 Top-N
    3. 置信度过滤：LLM 返回的 selected_skills 若不在候选中，过滤掉
    """

    # 决策置信度阈值（候选得分低于此值时，即使 LLM 选中也不加载）
    MIN_SCORE_THRESHOLD: float = 0.05
    # 最大加载 Skill 数（防止过度加载）
    MAX_SELECTED: int = 5

    def __init__(self) -> None:
        self._llm_router = None

    async def _get_router(self):
        if self._llm_router is None:
            from app.layers.agent_core.llm_router import LLMRouter

            self._llm_router = LLMRouter()
        return self._llm_router

    async def select(
        self,
        candidates: list[LoadCandidate],
        user_input: str,
        user_id: str,
        max_selected: int | None = None,
    ) -> LoadDecision:
        """执行 LLM 决策。

        Args:
            candidates: Top-K 候选列表（已排序）
            user_input: 用户输入
            user_id: 用户 ID
            max_selected: 最大选中数，默认 MAX_SELECTED

        Returns:
            LoadDecision
        """
        if not candidates:
            return LoadDecision()

        max_selected = max_selected or self.MAX_SELECTED

        # 构建决策 prompt
        system_prompt = self._build_system_prompt()
        user_prompt = self._build_user_prompt(candidates, user_input)

        try:
            router = await self._get_router()
            model_id = router.select_model("intent_recognition")
            result = await router.call_llm(user_prompt, model_id, system_prompt)
            raw = result.get("content", "")
            decision = LoadDecision.from_llm_response(raw)
        except Exception as e:
            logger.warning(f"SkillSelector LLM call failed: {e}, fallback to top-N")
            # 降级：按得分取 Top-N
            top_n = candidates[:max_selected]
            return LoadDecision(
                selected_skill_codes=[c.skill.skill_code for c in top_n],
                reason=f"fallback_top_{len(top_n)} (llm_error: {e})",
                raw_response="",
            )

        # 置信度过滤：LLM 选中的 Skill 必须在候选中且得分 >= 阈值
        candidate_map = {c.skill.skill_code: c for c in candidates}
        valid_codes: list[str] = []
        for code in decision.selected_skill_codes:
            cand = candidate_map.get(code)
            if cand and cand.final_score >= self.MIN_SCORE_THRESHOLD:
                valid_codes.append(code)
            else:
                logger.debug(
                    f"SkillSelector: filtered out {code} "
                    f"(in_candidates={cand is not None}, "
                    f"score={cand.final_score if cand else 'N/A'})"
                )

        # 限制最大选中数
        if len(valid_codes) > max_selected:
            logger.info(
                f"SkillSelector: truncating {len(valid_codes)} -> {max_selected} "
                f"(exceeds max_selected)"
            )
            valid_codes = valid_codes[:max_selected]

        decision.selected_skill_codes = valid_codes
        return decision

    def _build_system_prompt(self) -> str:
        """构建 system prompt。"""
        return (
            "你是 Skill 加载决策助手。根据用户输入，从候选 Skill 列表中选择需要加载的 Skill。\n"
            "选择原则：\n"
            "1. 只选择与用户意图明确相关的 Skill\n"
            "2. 避免过度加载，优先选择高优先级、高相关度的 Skill\n"
            "3. 如果没有合适的 Skill，返回空列表\n"
            "4. 最多选择 5 个 Skill\n\n"
            "返回 JSON 格式（严格遵循）：\n"
            "{\n"
            '  "selected_skills": ["SKILL-xxx", "SKILL-yyy"],\n'
            '  "reason": "简要说明选择原因"\n'
            "}\n"
        )

    def _build_user_prompt(
        self, candidates: list[LoadCandidate], user_input: str
    ) -> str:
        """构建 user prompt。"""
        skill_metas = [c.skill.to_prompt_meta() for c in candidates]
        return (
            f"用户输入：{user_input}\n\n"
            f"候选 Skill 列表（按相关度排序）：\n"
            f"{json.dumps(skill_metas, ensure_ascii=False, indent=2)}\n\n"
            "请选择需要加载的 Skill，返回 JSON。"
        )


# 模块级单例
skill_selector = SkillSelector()
