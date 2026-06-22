"""L2 Agent Core: HybridSkillExecutor & WorkflowExecutor — Hybrid/Workflow 型预留。

Per Skills管理需求规格文档 FR-6.4 / FR-6.5 / 实施计划 P5.4.

V1 阶段仅提供骨架实现，V2 阶段完善：
- HybridSkillExecutor: prompt + tool 组合（先注入 prompt 指导思路，再注册 tool 供 LLM 自主调用）
- WorkflowExecutor: 按 workflow.yaml DAG 定义执行节点，节点间状态传递
"""
from __future__ import annotations

import logging
import time
from typing import Any

from app.layers.agent_core.prompt_skill_executor import PromptSkillExecutor
from app.layers.agent_core.skill_executor import (
    SkillExecutionContext,
    SkillExecutionResult,
    SkillExecutor,
)
from app.layers.agent_core.tool_skill_executor import ToolSkillExecutor
from app.models.skill import SkillMeta

logger = logging.getLogger(__name__)


class HybridSkillExecutor(SkillExecutor):
    """Hybrid 型 Skill 执行器（prompt + tool 组合）。

    V1 预留骨架，V2 阶段完善：
    1. 先调用 PromptSkillExecutor 注入 system_prompt（指导思路）
    2. 再调用 ToolSkillExecutor 注册 tools（供 LLM 自主调用）
    3. 合并执行结果
    """

    def __init__(self) -> None:
        self._prompt_executor = PromptSkillExecutor()
        self._tool_executor = ToolSkillExecutor()

    @property
    def supported_type(self) -> str:
        return "hybrid"

    async def execute(
        self, skill: SkillMeta, context: SkillExecutionContext
    ) -> SkillExecutionResult:
        """执行 Hybrid 型 Skill。"""
        start_ts = time.monotonic()
        result = SkillExecutionResult(
            skill_code=skill.skill_code,
            skill_type=skill.skill_type,
            success=False,
        )

        try:
            # 1. 执行 prompt 部分
            prompt_result = await self._prompt_executor.execute(skill, context)
            if not prompt_result.success:
                result.error = f"Prompt phase failed: {prompt_result.error}"
                result.latency_ms = int((time.monotonic() - start_ts) * 1000)
                return result

            result.system_prompt = prompt_result.system_prompt

            # 2. 执行 tool 部分
            tool_result = await self._tool_executor.execute(skill, context)
            if tool_result.success:
                result.tools = tool_result.tools
                result.output = tool_result.output
            else:
                # tool 部分失败不阻塞 prompt 部分
                result.degraded = True
                result.error = f"Tool phase degraded: {tool_result.error}"

            result.success = True
            result.structured_output = prompt_result.structured_output
            result.latency_ms = int((time.monotonic() - start_ts) * 1000)

            logger.info(
                f"HybridSkillExecutor: executed skill={skill.skill_code} "
                f"latency={result.latency_ms}ms degraded={result.degraded}"
            )
            return result

        except Exception as e:
            result.error = f"Execution failed: {e}"
            result.latency_ms = int((time.monotonic() - start_ts) * 1000)
            logger.warning(
                f"HybridSkillExecutor: failed skill={skill.skill_code} error={e}"
            )
            return result


class WorkflowExecutor(SkillExecutor):
    """Workflow 型 Skill 执行器（DAG 流程编排）。

    V1 预留骨架，V2 阶段完善：
    1. 加载 workflow.yaml（DAG 定义）
    2. 拓扑排序节点
    3. 按顺序执行节点，节点间状态传递
    4. 支持条件分支、循环、并行
    """

    @property
    def supported_type(self) -> str:
        return "workflow"

    async def execute(
        self, skill: SkillMeta, context: SkillExecutionContext
    ) -> SkillExecutionResult:
        """执行 Workflow 型 Skill（V1 预留）。"""
        start_ts = time.monotonic()
        result = SkillExecutionResult(
            skill_code=skill.skill_code,
            skill_type=skill.skill_type,
            success=False,
            error="Workflow executor not implemented in V1 (reserved for V2)",
        )
        result.latency_ms = int((time.monotonic() - start_ts) * 1000)

        logger.info(
            f"WorkflowExecutor: V1 stub called skill={skill.skill_code} "
            f"(reserved for V2)"
        )
        return result
