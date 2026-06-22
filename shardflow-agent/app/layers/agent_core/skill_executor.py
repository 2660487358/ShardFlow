"""L2 Agent Core: SkillExecutor — Skill 执行器抽象接口。

Per Skills管理需求规格文档 FR-6 / 实施计划 P5.4.

定义 Skill 执行器的统一抽象接口，支持四种执行模式：
- prompt: 注入 system_prompt（PromptSkillExecutor）
- tool: 注册 tools 列表 + function call（ToolSkillExecutor）
- hybrid: prompt + tool 组合（HybridSkillExecutor，预留）
- workflow: DAG 流程编排（WorkflowExecutor，预留）

所有执行器继承此抽象基类，便于后续扩展。
"""
from __future__ import annotations

import abc
import logging
from dataclasses import dataclass, field
from typing import Any, AsyncIterator

from app.models.skill import SkillMeta

logger = logging.getLogger(__name__)


@dataclass
class SkillExecutionContext:
    """Skill 执行上下文。"""

    user_id: str
    session_id: str
    agent_id: str
    user_input: str = ""
    # 会话级变量（用于 prompt 模板渲染）
    variables: dict[str, Any] = field(default_factory=dict)
    # 当前对话历史
    messages: list[dict[str, Any]] = field(default_factory=list)
    # 超时（秒）
    timeout: float = 30.0


@dataclass
class SkillExecutionResult:
    """Skill 执行结果。"""

    skill_code: str
    skill_type: str
    success: bool
    # 注入的 system_prompt（prompt 型）
    system_prompt: str = ""
    # 注册的 tools 列表（tool 型）
    tools: list[dict[str, Any]] = field(default_factory=list)
    # 执行输出（function call 结果）
    output: Any = None
    # 结构化输出（按 output_schema 校验后）
    structured_output: dict[str, Any] | None = None
    # 错误信息
    error: str = ""
    # 性能指标
    latency_ms: int = 0
    tokens_used: int = 0
    # 降级标记
    degraded: bool = False


class SkillExecutor(abc.ABC):
    """Skill 执行器抽象接口。

    所有执行器必须实现 execute 方法。
    """

    @property
    @abc.abstractmethod
    def supported_type(self) -> str:
        """支持的 Skill 类型（prompt | tool | hybrid | workflow）。"""
        ...

    @abc.abstractmethod
    async def execute(
        self, skill: SkillMeta, context: SkillExecutionContext
    ) -> SkillExecutionResult:
        """执行 Skill。

        Args:
            skill: Skill 元数据
            context: 执行上下文

        Returns:
            执行结果
        """
        ...

    async def validate_input(
        self, skill: SkillMeta, input_data: dict[str, Any]
    ) -> tuple[bool, str]:
        """校验输入参数（按 input_schema）。

        V1 简化：只校验必填字段是否存在。
        V2 阶段替换为 jsonschema 完整校验。
        """
        if not skill.input_schema:
            return True, ""
        required = skill.input_schema.get("required", [])
        if not required:
            return True, ""
        missing = [field for field in required if field not in input_data]
        if missing:
            return False, f"Missing required fields: {missing}"
        return True, ""

    async def validate_output(
        self, skill: SkillMeta, output_data: dict[str, Any]
    ) -> tuple[bool, str]:
        """校验输出结构（按 output_schema）。

        V1 简化：只校验必填字段是否存在。
        V2 阶段替换为 jsonschema 完整校验。
        """
        if not skill.output_schema:
            return True, ""
        required = skill.output_schema.get("required", [])
        if not required:
            return True, ""
        missing = [field for field in required if field not in output_data]
        if missing:
            return False, f"Missing required output fields: {missing}"
        return True, ""


class SkillExecutorRegistry:
    """Skill 执行器注册表。

    按 skill_type 路由到对应的执行器。
    """

    def __init__(self) -> None:
        self._executors: dict[str, SkillExecutor] = {}

    def register(self, executor: SkillExecutor) -> None:
        """注册执行器。"""
        self._executors[executor.supported_type] = executor
        logger.info(f"Registered SkillExecutor for type={executor.supported_type}")

    def get(self, skill_type: str) -> SkillExecutor | None:
        """获取执行器。"""
        return self._executors.get(skill_type)

    async def execute(
        self, skill: SkillMeta, context: SkillExecutionContext
    ) -> SkillExecutionResult:
        """按 skill_type 路由执行。"""
        executor = self.get(skill.skill_type)
        if executor is None:
            return SkillExecutionResult(
                skill_code=skill.skill_code,
                skill_type=skill.skill_type,
                success=False,
                error=f"Unsupported skill type: {skill.skill_type}",
            )
        return await executor.execute(skill, context)


# 模块级单例
skill_executor_registry = SkillExecutorRegistry()
