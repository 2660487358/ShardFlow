"""L2 Agent Core: PromptSkillExecutor — Prompt 型 Skill 执行器。

Per Skills管理需求规格文档 FR-6.2 / FR-6.7 / 实施计划 P5.2.

职责：
- 加载 prompt.md（从 MinIO/Redis 读取）
- 渲染 prompt 模板（变量替换）
- 注入 system_prompt（会话级注入）
- 按 output_schema 输出（结构化输出）
"""
from __future__ import annotations

import logging
import re
import time
from typing import Any

from app.layers.agent_core.skill_artifact_loader import skill_artifact_loader
from app.layers.agent_core.skill_cache import skill_cache
from app.layers.agent_core.skill_executor import (
    SkillExecutionContext,
    SkillExecutionResult,
    SkillExecutor,
)
from app.models.skill import SkillMeta

logger = logging.getLogger(__name__)


class PromptSkillExecutor(SkillExecutor):
    """Prompt 型 Skill 执行器。

    执行流程：
    1. 从缓存加载 SkillMeta（L1 -> L2 -> L3）
    2. 从 MinIO 加载 prompt.md
    3. 渲染模板（变量替换 {{var}}）
    4. 注入 system_prompt 到当前会话
    5. （可选）按 output_schema 调用 LLM 生成结构化输出
    """

    @property
    def supported_type(self) -> str:
        return "prompt"

    async def execute(
        self, skill: SkillMeta, context: SkillExecutionContext
    ) -> SkillExecutionResult:
        """执行 Prompt 型 Skill。"""
        start_ts = time.monotonic()
        result = SkillExecutionResult(
            skill_code=skill.skill_code,
            skill_type=skill.skill_type,
            success=False,
        )

        try:
            # 1. 加载 prompt.md
            prompt_content = await skill_artifact_loader.load_prompt_md(
                skill, timeout=context.timeout
            )
            if prompt_content is None:
                result.error = "Failed to load prompt.md"
                result.latency_ms = int((time.monotonic() - start_ts) * 1000)
                return result

            # 2. 渲染模板
            rendered_prompt = self._render_template(prompt_content, skill, context)
            if not rendered_prompt:
                result.error = "Template rendering produced empty result"
                result.latency_ms = int((time.monotonic() - start_ts) * 1000)
                return result

            # 3. 注入 system_prompt
            result.system_prompt = rendered_prompt
            result.success = True

            # 4. 按 output_schema 输出（如果定义了 output_schema）
            if skill.output_schema:
                structured = await self._generate_structured_output(
                    skill, rendered_prompt, context
                )
                if structured is not None:
                    result.structured_output = structured
                    # 校验输出
                    valid, err = await self.validate_output(skill, structured)
                    if not valid:
                        logger.warning(
                            f"PromptSkillExecutor: output validation failed "
                            f"skill={skill.skill_code} error={err}"
                        )
                        result.degraded = True
                        result.error = err

            result.latency_ms = int((time.monotonic() - start_ts) * 1000)
            logger.info(
                f"PromptSkillExecutor: executed skill={skill.skill_code} "
                f"latency={result.latency_ms}ms"
            )
            return result

        except Exception as e:
            result.error = f"Execution failed: {e}"
            result.latency_ms = int((time.monotonic() - start_ts) * 1000)
            logger.warning(
                f"PromptSkillExecutor: failed skill={skill.skill_code} error={e}"
            )
            return result

    # ------------------------------------------------------------------
    # 模板渲染
    # ------------------------------------------------------------------

    def _render_template(
        self,
        template: str,
        skill: SkillMeta,
        context: SkillExecutionContext,
    ) -> str:
        """渲染 prompt 模板。

        支持变量替换：
        - {{user_input}}: 用户输入
        - {{session_id}}: 会话 ID
        - {{agent_id}}: Agent ID
        - {{user_id}}: 用户 ID
        - {{skill_name}}: Skill 名称
        - {{skill_code}}: Skill 编码
        - {{var:xxx}}: 自定义变量（从 context.variables 取）
        - {{config:xxx}}: Skill 配置项（从 skill.config 取）
        - {{override:xxx}}: Agent 级配置覆盖（从 skill.config_override 取）
        """
        if not template:
            return ""

        # 合并变量
        variables: dict[str, Any] = {
            "user_input": context.user_input,
            "session_id": context.session_id,
            "agent_id": context.agent_id,
            "user_id": context.user_id,
            "skill_name": skill.skill_name,
            "skill_code": skill.skill_code,
        }
        variables.update(context.variables)

        # 渲染 {{var:xxx}} 自定义变量
        def replace_var(match: re.Match) -> str:
            key = match.group(1)
            value = variables.get(key, "")
            return str(value) if value is not None else ""

        rendered = re.sub(r"\{\{(\w+)\}\}", replace_var, template)

        # 渲染 {{var:xxx}} 自定义变量
        def replace_custom_var(match: re.Match) -> str:
            key = match.group(1)
            value = context.variables.get(key, "")
            return str(value) if value is not None else ""

        rendered = re.sub(r"\{\{var:(\w+)\}\}", replace_custom_var, rendered)

        # 渲染 {{config:xxx}} Skill 配置
        def replace_config(match: re.Match) -> str:
            key = match.group(1)
            value = skill.config.get(key, "")
            return str(value) if value is not None else ""

        rendered = re.sub(r"\{\{config:(\w+)\}\}", replace_config, rendered)

        # 渲染 {{override:xxx}} Agent 级配置覆盖
        def replace_override(match: re.Match) -> str:
            key = match.group(1)
            value = skill.config_override.get(key, skill.config.get(key, ""))
            return str(value) if value is not None else ""

        rendered = re.sub(r"\{\{override:(\w+)\}\}", replace_override, rendered)

        return rendered.strip()

    # ------------------------------------------------------------------
    # 结构化输出
    # ------------------------------------------------------------------

    async def _generate_structured_output(
        self,
        skill: SkillMeta,
        system_prompt: str,
        context: SkillExecutionContext,
    ) -> dict[str, Any] | None:
        """按 output_schema 调用 LLM 生成结构化输出。

        V1 简化：在 system_prompt 后追加 output_schema 要求，让 LLM 输出 JSON。
        V2 阶段替换为 function call / response_format=json_schema。
        """
        import json

        try:
            from app.layers.agent_core.llm_router import LLMRouter

            router = LLMRouter()
            model_id = router.select_model("think")

            output_schema_str = json.dumps(skill.output_schema, ensure_ascii=False)
            user_prompt = (
                f"请按照以下 JSON Schema 输出结构化结果：\n{output_schema_str}\n\n"
                f"用户输入：{context.user_input}\n\n"
                "只返回 JSON，不要其他内容。"
            )

            result = await router.call_llm(user_prompt, model_id, system_prompt)
            raw = result.get("content", "")
            if not raw:
                return None

            # 解析 JSON（容忍 markdown 代码块）
            text = raw.strip()
            if text.startswith("```"):
                parts = text.split("```", 2)
                if len(parts) >= 2:
                    text = parts[1]
                    if text.startswith("json"):
                        text = text[4:]
                    text = text.strip()

            return json.loads(text)

        except Exception as e:
            logger.warning(
                f"PromptSkillExecutor: structured output generation failed "
                f"skill={skill.skill_code} error={e}"
            )
            return None
