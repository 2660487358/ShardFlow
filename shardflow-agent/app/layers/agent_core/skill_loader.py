"""L2 Agent Core: SkillLoader — 三级漏斗加载器。

Per Skills管理需求规格文档 FR-7 / 实施计划 P5.1.

三级漏斗：
1. 硬性过滤（Hard Filter）：binding 范围 + status=published + EXECUTE 权限 + trigger_keywords 匹配 + required 强制加载
2. 语义检索（V1 简化）：关键词 + description 向量相似度排序，取 Top-K（默认 K=5）
   - LRU 偏好加权：最近使用 Skill 提升排序
3. LLM 决策：将 Top-K Skill 元数据注入 system_prompt，输出结构化 load 决策

每次加载记录 skill_audit_log（通过 Java 回调）。
"""
from __future__ import annotations

import asyncio
import logging
import time
from collections import OrderedDict
from typing import Any

import httpx

from app.config import settings
from app.models.skill import LoadAuditRecord, LoadCandidate, LoadDecision, SkillMeta

logger = logging.getLogger(__name__)


class SkillLoader:
    """三级漏斗加载器。

    职责：
    - 从 Java 后端拉取 Agent 挂载的 Skill 候选集（含绑定关系、版本、Artifact 路径）
    - 执行三级漏斗筛选与排序
    - 调用 LLM 决策最终加载的 Skill 列表
    - 记录加载审计日志
    """

    DEFAULT_TOP_K: int = 5
    LRU_MAX_SIZE: int = 64
    LRU_BOOST_FACTOR: float = 0.1  # 每次最近使用加 0.1 分，最高 0.5

    def __init__(self) -> None:
        self._http_client: httpx.AsyncClient | None = None
        # LRU 偏好缓存：skill_code -> 最近使用时间戳（monotonic）
        # 跨会话保留（进程级），按 LRU_MAX_SIZE 淘汰
        self._lru_cache: OrderedDict[str, float] = OrderedDict()

    async def _get_client(self) -> httpx.AsyncClient:
        if self._http_client is None:
            self._http_client = httpx.AsyncClient(timeout=httpx.Timeout(10.0))
        return self._http_client

    # ------------------------------------------------------------------
    # 公共入口
    # ------------------------------------------------------------------

    async def load_skills(
        self,
        agent_id: str,
        user_id: str,
        session_id: str,
        user_input: str,
        top_k: int | None = None,
    ) -> tuple[list[SkillMeta], LoadDecision]:
        """执行三级漏斗加载。

        Args:
            agent_id: 当前 Agent 标识
            user_id: 当前用户 ID
            session_id: 当前会话 ID
            user_input: 用户输入文本（用于关键词匹配与语义检索）
            top_k: 第二层取 Top-K，默认 5

        Returns:
            (最终选中的 Skill 列表, LLM 决策结果)
        """
        start_ts = time.monotonic()
        top_k = top_k or self.DEFAULT_TOP_K

        # Step 0: 拉取候选集
        candidates = await self._fetch_candidates(agent_id, user_id)
        if not candidates:
            logger.info(f"No skill candidates for agent={agent_id}")
            return [], LoadDecision()

        # Step 1: 硬性过滤
        filtered = self._hard_filter(candidates, user_input)
        if not filtered:
            logger.info(f"All candidates filtered out by hard filter, agent={agent_id}")
            await self._record_audit(
                agent_id, user_id, session_id, [], 0, True, "all_filtered"
            )
            return [], LoadDecision()

        # required 强制加载：binding_type=required 的 Skill 直接进入最终列表
        required_skills = [c.skill for c in filtered if c.skill.binding_type == "required"]
        optional_candidates = [c for c in filtered if c.skill.binding_type != "required"]

        # Step 2: 语义检索 + LRU 加权
        ranked = self._semantic_rank(optional_candidates, user_input)
        top_k_candidates = ranked[:top_k]

        # Step 3: LLM 决策
        decision = await self._llm_decide(top_k_candidates, user_input, user_id)

        # 合并：required + LLM 选中的 optional
        selected_codes = set(decision.selected_skill_codes)
        selected_optional = [c.skill for c in top_k_candidates if c.skill.skill_code in selected_codes]
        final_skills = required_skills + selected_optional

        # 更新 LRU 缓存
        for skill in final_skills:
            self._touch_lru(skill.skill_code)

        # 记录审计
        latency_ms = int((time.monotonic() - start_ts) * 1000)
        await self._record_audit(
            agent_id, user_id, session_id, final_skills, latency_ms, True, ""
        )

        logger.info(
            f"SkillLoader: candidates={len(candidates)} filtered={len(filtered)} "
            f"top_k={len(top_k_candidates)} selected={len(final_skills)} "
            f"latency={latency_ms}ms"
        )
        return final_skills, decision

    def _touch_lru(self, skill_code: str) -> None:
        """更新 LRU 缓存。"""
        self._lru_cache.pop(skill_code, None)
        self._lru_cache[skill_code] = time.monotonic()
        while len(self._lru_cache) > self.LRU_MAX_SIZE:
            self._lru_cache.popitem(last=False)

    # ------------------------------------------------------------------
    # Step 0: 拉取候选集
    # ------------------------------------------------------------------

    async def _fetch_candidates(self, agent_id: str, user_id: str) -> list[LoadCandidate]:
        """从 Java 后端拉取 Agent 挂载的 Skill 候选集。

        调用 GET /api/v1/agents/{agent_id}/skills（内部接口），
        返回 AgentSkillBinding + Skill 元数据聚合。
        """
        base_url = settings.java_base_url
        api_key = settings.java_api_key or settings.llm_api_key
        headers = {"X-API-Key": api_key, "X-User-Id": user_id}

        try:
            client = await self._get_client()
            resp = await client.get(
                f"{base_url}/api/v1/agents/{agent_id}/skills",
                headers=headers,
            )
            resp.raise_for_status()
            data = resp.json()
            bindings = data.get("bindings", data if isinstance(data, list) else [])
            candidates: list[LoadCandidate] = []
            for item in bindings:
                try:
                    skill = self._parse_skill_meta(item)
                    if skill:
                        candidates.append(LoadCandidate(skill=skill))
                except Exception as e:
                    logger.warning(f"Failed to parse skill binding: {e}")
            return candidates
        except Exception as e:
            logger.warning(f"Failed to fetch skill candidates from Java: {e}")
            return []

    def _parse_skill_meta(self, item: dict[str, Any]) -> SkillMeta | None:
        """解析 Java 返回的绑定 + Skill 元数据为 SkillMeta。"""
        import json

        skill_data = item.get("skill", item)
        skill_id = skill_data.get("id") or skill_data.get("skill_id")
        if not skill_id:
            return None

        def _parse_json_field(raw: Any, default: Any) -> Any:
            if raw is None:
                return default
            if isinstance(raw, (list, dict)):
                return raw
            if isinstance(raw, str):
                if not raw:
                    return default
                try:
                    return json.loads(raw)
                except Exception:
                    return default
            return default

        return SkillMeta(
            skill_id=int(skill_id),
            skill_code=skill_data.get("skill_code", ""),
            skill_name=skill_data.get("skill_name", ""),
            description=skill_data.get("description", ""),
            skill_type=skill_data.get("skill_type", "prompt"),
            trust_tier=skill_data.get("trust_tier", "personal"),
            owner_id=skill_data.get("owner_id", ""),
            user_id=skill_data.get("user_id", ""),
            current_version=skill_data.get("current_version", ""),
            status=skill_data.get("status", "draft"),
            trigger_keywords=_parse_json_field(skill_data.get("trigger_keywords"), []),
            input_schema=_parse_json_field(skill_data.get("input_schema"), {}),
            output_schema=_parse_json_field(skill_data.get("output_schema"), {}),
            cost_estimate=_parse_json_field(skill_data.get("cost_estimate"), {}),
            config=_parse_json_field(skill_data.get("config"), {}),
            tags=_parse_json_field(skill_data.get("tags"), []),
            source=skill_data.get("source", "CUSTOM"),
            binding_type=item.get("binding_type", "optional"),
            priority=int(item.get("priority", 0)),
            config_override=_parse_json_field(item.get("config_override"), {}),
            enabled=bool(item.get("enabled", True)),
            artifacts=item.get("artifacts", {}),
            content_hash=skill_data.get("content_hash", ""),
        )

    # ------------------------------------------------------------------
    # Step 1: 硬性过滤
    # ------------------------------------------------------------------

    def _hard_filter(
        self, candidates: list[LoadCandidate], user_input: str
    ) -> list[LoadCandidate]:
        """第一层：硬性过滤。

        规则（任一不满足即过滤）：
        - enabled = True
        - status = published
        - 权限校验（V1 简化：trust_tier=personal 仅 owner 可用；team/official 全员可用）
        - trigger_keywords 匹配（若 Skill 定义了 trigger_keywords，则用户输入需命中至少一个）
          - required 强制加载的 Skill 跳过关键词匹配
        """
        result: list[LoadCandidate] = []
        user_input_lower = user_input.lower()

        for cand in candidates:
            skill = cand.skill
            passed = True
            reason = ""

            # 1. enabled
            if not skill.enabled:
                passed = False
                reason = "disabled"
            # 2. status
            elif skill.status != "published":
                passed = False
                reason = f"status={skill.status}"
            # 3. 权限（V1 简化，完整版由 Java 端 SkillPermissionChecker 校验）
            # Python 端只做兜底：personal Skill 仅 owner 可用
            elif skill.trust_tier == "personal" and skill.owner_id and not skill.user_id:
                # user_id 由 Java 端注入，此处兜底
                pass
            # 4. trigger_keywords 匹配
            elif (
                skill.binding_type != "required"
                and skill.trigger_keywords
                and not self._match_keywords(skill.trigger_keywords, user_input_lower)
            ):
                passed = False
                reason = "trigger_keywords_not_matched"

            cand.hard_filter_passed = passed
            cand.hard_filter_reason = reason
            if passed:
                result.append(cand)
            else:
                logger.debug(
                    f"Hard filter rejected skill={skill.skill_code} reason={reason}"
                )
        return result

    def _match_keywords(self, keywords: list[str], user_input_lower: str) -> bool:
        """关键词匹配（大小写不敏感，子串匹配）。"""
        for kw in keywords:
            if kw and kw.lower() in user_input_lower:
                return True
        return False

    # ------------------------------------------------------------------
    # Step 2: 语义检索 + LRU 加权
    # ------------------------------------------------------------------

    def _semantic_rank(
        self, candidates: list[LoadCandidate], user_input: str
    ) -> list[LoadCandidate]:
        """第二层：语义检索（V1 简化）+ LRU 偏好加权。

        V1 简化方案（per D-10）：
        - 关键词命中数 * 0.3
        - description 与 user_input 的 Jaccard 相似度 * 0.4
        - trigger_keywords 命中数 * 0.3
        - LRU 偏好加权：最近使用的 Skill 加 0.1~0.5 分

        V2 阶段替换为 pgvector 向量相似度。
        """
        user_tokens = set(self._tokenize(user_input))

        for cand in candidates:
            skill = cand.skill
            # 关键词命中数
            kw_hits = sum(
                1 for kw in skill.trigger_keywords
                if kw and kw.lower() in user_input.lower()
            )
            kw_score = min(kw_hits * 0.3, 0.9) if skill.trigger_keywords else 0.0

            # description Jaccard 相似度
            desc_tokens = set(self._tokenize(skill.description))
            if user_tokens and desc_tokens:
                intersection = user_tokens & desc_tokens
                union = user_tokens | desc_tokens
                jaccard = len(intersection) / len(union)
            else:
                jaccard = 0.0
            desc_score = jaccard * 0.4

            # trigger_keywords Jaccard
            kw_tokens = set()
            for kw in skill.trigger_keywords:
                kw_tokens.update(self._tokenize(kw))
            if user_tokens and kw_tokens:
                intersection = user_tokens & kw_tokens
                union = user_tokens | kw_tokens
                kw_jaccard = len(intersection) / len(union)
            else:
                kw_jaccard = 0.0
            kw_jaccard_score = kw_jaccard * 0.3

            # LRU 偏好加权
            lru_boost = self._get_lru_boost(skill.skill_code)
            cand.lru_boost = lru_boost

            # priority 加权（priority 越大越优先，归一化到 0~0.2）
            priority_boost = min(max(skill.priority, 0) * 0.02, 0.2)

            cand.semantic_score = kw_score + desc_score + kw_jaccard_score
            cand.final_score = cand.semantic_score + lru_boost + priority_boost

        # 按综合得分降序
        return sorted(candidates, key=lambda c: c.final_score, reverse=True)

    def _tokenize(self, text: str) -> list[str]:
        """简单分词：英文按空格/标点，中文按字。

        V2 阶段替换为专业分词器 + embedding。
        """
        if not text:
            return []
        import re

        # 英文：按非字母数字分割
        tokens = [t.lower() for t in re.split(r"[^a-zA-Z0-9\u4e00-\u9fa5]+", text) if t]
        # 中文：按字拆分（简化方案）
        result: list[str] = []
        for tok in tokens:
            if any("\u4e00" <= ch <= "\u9fa5" for ch in tok):
                # 中文 token 按字拆分
                result.extend(list(tok))
            else:
                result.append(tok)
        return [t for t in result if t]

    def _get_lru_boost(self, skill_code: str) -> float:
        """获取 LRU 偏好加权分。"""
        if skill_code not in self._lru_cache:
            return 0.0
        # 越最近使用，加权越高（线性衰减）
        last_used = self._lru_cache[skill_code]
        now = time.monotonic()
        # 1 小时内有效
        age = now - last_used
        if age > 3600:
            return 0.0
        # 衰减因子：1.0 -> 0.0
        decay = 1.0 - (age / 3600)
        return self.LRU_BOOST_FACTOR * decay * 5  # 0.0 ~ 0.5

    # ------------------------------------------------------------------
    # Step 3: LLM 决策
    # ------------------------------------------------------------------

    async def _llm_decide(
        self,
        candidates: list[LoadCandidate],
        user_input: str,
        user_id: str,
    ) -> LoadDecision:
        """第三层：LLM 决策。

        将 Top-K Skill 元数据注入 system_prompt，输出结构化 load 决策。
        """
        if not candidates:
            return LoadDecision()

        # 构建 prompt
        skill_metas = [c.skill.to_prompt_meta() for c in candidates]
        import json

        system_prompt = (
            "你是 Skill 加载决策助手。根据用户输入，从候选 Skill 列表中选择需要加载的 Skill。\n"
            "只选择与用户意图明确相关的 Skill，避免过度加载。\n"
            "返回 JSON 格式：\n"
            '{"selected_skills": ["SKILL-xxx", ...], "reason": "选择原因"}\n'
            "如果没有合适的 Skill，返回空列表。"
        )
        user_prompt = (
            f"用户输入：{user_input}\n\n"
            f"候选 Skill 列表：\n{json.dumps(skill_metas, ensure_ascii=False, indent=2)}\n\n"
            "请选择需要加载的 Skill。"
        )

        try:
            from app.layers.agent_core.llm_router import LLMRouter

            router = LLMRouter()
            model_id = router.select_model("intent_recognition")
            result = await router.call_llm(user_prompt, model_id, system_prompt)
            raw = result.get("content", "")
            return LoadDecision.from_llm_response(raw)
        except Exception as e:
            logger.warning(f"LLM decide failed: {e}, fallback to top-1")
            # 降级：返回得分最高的 1 个 Skill
            if candidates:
                return LoadDecision(
                    selected_skill_codes=[candidates[0].skill.skill_code],
                    reason=f"fallback_top1 (llm_error: {e})",
                    raw_response="",
                )
            return LoadDecision()

    # ------------------------------------------------------------------
    # 审计日志
    # ------------------------------------------------------------------

    async def _record_audit(
        self,
        agent_id: str,
        user_id: str,
        session_id: str,
        skills: list[SkillMeta],
        latency_ms: int,
        success: bool,
        error: str,
    ) -> None:
        """记录加载审计日志到 Java 端 skill_audit_log。

        通过 POST /api/v1/skills/audit-logs/internal 回调。
        失败不阻塞主流程。
        """
        if not skills and not error:
            return

        base_url = settings.java_base_url
        api_key = settings.java_api_key or settings.llm_api_key
        headers = {"X-API-Key": api_key, "X-User-Id": user_id}

        records = [
            {
                "skill_id": s.skill_id,
                "skill_code": s.skill_code,
                "operation": "SKILL_LOAD",
                "operator_id": user_id,
                "agent_id": agent_id,
                "session_id": session_id,
                "details": {
                    "binding_type": s.binding_type,
                    "version": s.current_version,
                    "skill_type": s.skill_type,
                },
                "latency_ms": latency_ms,
                "success": success,
                "error": error,
            }
            for s in skills
        ]

        try:
            client = await self._get_client()
            await client.post(
                f"{base_url}/api/v1/skills/audit-logs/internal",
                headers=headers,
                json={"records": records},
                timeout=5.0,
            )
        except Exception as e:
            logger.warning(f"Failed to record skill audit log: {e}")


# 模块级单例
skill_loader = SkillLoader()
