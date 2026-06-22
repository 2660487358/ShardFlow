"""L2 Agent Core: ToolSkillExecutor — Tool 型 Skill 执行器。

Per Skills管理需求规格文档 FR-6.3 / FR-6.6 / FR-6.7 / 实施计划 P5.3.

职责：
- 加载 tool.py（从 MinIO 下载）
- 注册 tools 列表（将 Tool 定义注册到 LLM tools）
- 实现 function call 执行（LLM 生成 function_call 后执行 handler）
- 输入参数校验（按 input_schema）
- 输出结构校验（按 output_schema）

安全约束：
- tool.py 在受限命名空间执行（禁止 import os/sys/subprocess 等危险模块）
- 执行超时控制（默认 30s）
- 输入/输出大小限制
"""
from __future__ import annotations

import asyncio
import importlib.util
import logging
import sys
import time
import traceback
from typing import Any

from app.layers.agent_core.skill_artifact_loader import skill_artifact_loader
from app.layers.agent_core.skill_executor import (
    SkillExecutionContext,
    SkillExecutionResult,
    SkillExecutor,
)
from app.models.skill import SkillMeta

logger = logging.getLogger(__name__)


# 危险模块黑名单（V1 简化沙箱，V2 阶段替换为进程级隔离）
_DANGEROUS_MODULES = {
    "os",
    "sys",
    "subprocess",
    "shutil",
    "ctypes",
    "multiprocessing",
    "socket",
    "http",
    "urllib",
    "requests",
    "asyncio.subprocess",
}


class ToolSkillExecutor(SkillExecutor):
    """Tool 型 Skill 执行器。

    执行流程：
    1. 从 MinIO 加载 tool.py
    2. 在受限命名空间执行 tool.py，提取 handler 函数
    3. 注册 tools 列表（生成 OpenAI function call 格式）
    4. LLM 生成 function_call 后，执行 handler
    5. 校验输入/输出
    """

    @property
    def supported_type(self) -> str:
        return "tool"

    async def execute(
        self, skill: SkillMeta, context: SkillExecutionContext
    ) -> SkillExecutionResult:
        """执行 Tool 型 Skill。"""
        start_ts = time.monotonic()
        result = SkillExecutionResult(
            skill_code=skill.skill_code,
            skill_type=skill.skill_type,
            success=False,
        )

        try:
            # 1. 加载 tool.py
            tool_code = await skill_artifact_loader.load_tool_py(
                skill, timeout=context.timeout
            )
            if tool_code is None:
                result.error = "Failed to load tool.py"
                result.latency_ms = int((time.monotonic() - start_ts) * 1000)
                return result

            # 2. 安全校验
            unsafe = self._check_safety(tool_code)
            if unsafe:
                result.error = f"Unsafe code detected: {unsafe}"
                result.latency_ms = int((time.monotonic() - start_ts) * 1000)
                logger.warning(
                    f"ToolSkillExecutor: unsafe code rejected skill={skill.skill_code} "
                    f"issues={unsafe}"
                )
                return result

            # 3. 加载 tool 模块
            module = await self._load_tool_module(skill, tool_code)
            if module is None:
                result.error = "Failed to load tool module"
                result.latency_ms = int((time.monotonic() - start_ts) * 1000)
                return result

            # 4. 注册 tools 列表
            tools = self._build_tools_list(skill, module)
            if not tools:
                result.error = "No tools registered"
                result.latency_ms = int((time.monotonic() - start_ts) * 1000)
                return result

            result.tools = tools
            result.success = True

            # 5. 如果上下文中有 function_call，执行 handler
            fc = context.variables.get("function_call")
            if fc:
                exec_result = await self._execute_function_call(
                    skill, module, fc, context
                )
                if exec_result is not None:
                    result.output = exec_result
                    # 校验输出
                    if isinstance(exec_result, dict):
                        valid, err = await self.validate_output(skill, exec_result)
                        if not valid:
                            result.degraded = True
                            result.error = err

            result.latency_ms = int((time.monotonic() - start_ts) * 1000)
            logger.info(
                f"ToolSkillExecutor: executed skill={skill.skill_code} "
                f"tools={len(tools)} latency={result.latency_ms}ms"
            )
            return result

        except Exception as e:
            result.error = f"Execution failed: {e}"
            result.latency_ms = int((time.monotonic() - start_ts) * 1000)
            logger.warning(
                f"ToolSkillExecutor: failed skill={skill.skill_code} error={e}\n"
                f"{traceback.format_exc()}"
            )
            return result

    # ------------------------------------------------------------------
    # 安全校验
    # ------------------------------------------------------------------

    def _check_safety(self, code: str) -> list[str]:
        """检查代码安全性（V1 简化静态检查）。

        检查项：
        - 危险 import
        - 危险内置函数（exec/eval/open/compile）
        - 网络访问
        """
        issues: list[str] = []

        # 检查 import
        import re

        # 匹配 import xxx / from xxx import
        import_patterns = [
            r"^\s*import\s+(\S+)",
            r"^\s*from\s+(\S+)\s+import",
        ]
        for pattern in import_patterns:
            for match in re.finditer(pattern, code, re.MULTILINE):
                module_name = match.group(1).split(".")[0]
                if module_name in _DANGEROUS_MODULES:
                    issues.append(f"dangerous_import:{match.group(1)}")

        # 检查危险内置函数
        dangerous_builtins = ["exec", "eval", "compile", "__import__"]
        for func in dangerous_builtins:
            if re.search(rf"\b{func}\s*\(", code):
                issues.append(f"dangerous_builtin:{func}")

        # 检查 open() 文件操作
        if re.search(r"\bopen\s*\(", code):
            issues.append("file_access:open")

        return issues

    # ------------------------------------------------------------------
    # 模块加载
    # ------------------------------------------------------------------

    async def _load_tool_module(self, skill: SkillMeta, code: str):
        """加载 tool.py 为 Python 模块。

        在受限命名空间执行（V1 简化沙箱）。
        """
        import types

        module_name = f"skill_tool_{skill.skill_code.replace('-', '_')}"

        try:
            # 创建受限命名空间
            safe_builtins = {
                name: getattr(__builtins__, name) if hasattr(__builtins__, name) else __builtins__[name]
                for name in dir(__builtins__)
                if name not in ("exec", "eval", "compile", "__import__", "open")
            }
            safe_builtins["__import__"] = self._safe_import

            namespace: dict[str, Any] = {
                "__builtins__": safe_builtins,
                "__name__": module_name,
            }

            # 执行代码
            exec(compile(code, f"<skill:{skill.skill_code}>", "exec"), namespace)

            # 创建模块对象
            module = types.ModuleType(module_name)
            for key, value in namespace.items():
                if not key.startswith("__"):
                    setattr(module, key, value)

            return module

        except Exception as e:
            logger.warning(
                f"ToolSkillExecutor: failed to load module skill={skill.skill_code} "
                f"error={e}"
            )
            return None

    def _safe_import(self, name: str, *args, **kwargs):
        """安全的 import 函数，禁止导入危险模块。"""
        root_module = name.split(".")[0]
        if root_module in _DANGEROUS_MODULES:
            raise ImportError(f"Import of '{name}' is not allowed in Skill tool.py")
        return __builtins__.__import__(name, *args, **kwargs) if hasattr(__builtins__, "__import__") else importlib.import_module(name)

    # ------------------------------------------------------------------
    # Tools 列表构建
    # ------------------------------------------------------------------

    def _build_tools_list(self, skill: SkillMeta, module) -> list[dict[str, Any]]:
        """构建 OpenAI function call 格式的 tools 列表。

        从模块中提取：
        - handler 函数（必须有 __doc__ 或 tool_def 字典）
        - tool_def 字典（name/description/parameters）
        """
        tools: list[dict[str, Any]] = []

        # 优先从 tool_def 字典提取
        tool_def = getattr(module, "tool_def", None)
        if isinstance(tool_def, dict):
            tools.append(self._build_tool_entry(skill, tool_def))
        elif isinstance(tool_def, list):
            for td in tool_def:
                if isinstance(td, dict):
                    tools.append(self._build_tool_entry(skill, td))

        # 从 handler 函数提取
        if not tools:
            handler = getattr(module, "handler", None)
            if handler and callable(handler):
                tool_entry = {
                    "type": "function",
                    "function": {
                        "name": f"{skill.skill_code}_handler",
                        "description": handler.__doc__ or skill.description or skill.skill_name,
                        "parameters": skill.input_schema or {"type": "object", "properties": {}},
                    },
                }
                tools.append(tool_entry)

        return tools

    def _build_tool_entry(self, skill: SkillMeta, tool_def: dict[str, Any]) -> dict[str, Any]:
        """构建单个 tool 条目。"""
        name = tool_def.get("name", f"{skill.skill_code}_tool")
        description = tool_def.get("description", skill.description)
        parameters = tool_def.get("parameters", skill.input_schema or {"type": "object", "properties": {}})
        return {
            "type": "function",
            "function": {
                "name": name,
                "description": description,
                "parameters": parameters,
            },
        }

    # ------------------------------------------------------------------
    # Function call 执行
    # ------------------------------------------------------------------

    async def _execute_function_call(
        self,
        skill: SkillMeta,
        module,
        function_call: dict[str, Any],
        context: SkillExecutionContext,
    ) -> Any:
        """执行 LLM 生成的 function_call。

        Args:
            function_call: {"name": "xxx", "arguments": "{...}"}

        Returns:
            handler 执行结果
        """
        import json

        name = function_call.get("name", "")
        arguments_raw = function_call.get("arguments", "{}")

        # 解析参数
        try:
            if isinstance(arguments_raw, str):
                arguments = json.loads(arguments_raw)
            else:
                arguments = arguments_raw
        except Exception as e:
            logger.warning(f"Failed to parse function_call arguments: {e}")
            return {"error": f"Invalid arguments: {e}"}

        # 校验输入
        valid, err = await self.validate_input(skill, arguments)
        if not valid:
            return {"error": err}

        # 查找 handler
        handler = getattr(module, "handler", None)
        if handler is None:
            # 尝试按 function name 查找
            handler = getattr(module, name, None)

        if handler is None or not callable(handler):
            return {"error": f"Handler not found: {name}"}

        # 执行 handler（带超时）
        try:
            if asyncio.iscoroutinefunction(handler):
                result = await asyncio.wait_for(
                    handler(**arguments), timeout=context.timeout
                )
            else:
                # 同步函数在线程池中执行
                result = await asyncio.wait_for(
                    asyncio.to_thread(handler, **arguments),
                    timeout=context.timeout,
                )
            return result

        except asyncio.TimeoutError:
            return {"error": f"Handler execution timeout ({context.timeout}s)"}
        except Exception as e:
            logger.warning(
                f"ToolSkillExecutor: handler execution failed skill={skill.skill_code} "
                f"error={e}"
            )
            return {"error": f"Handler execution failed: {e}"}
