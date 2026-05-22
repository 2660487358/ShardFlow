# mypy: ignore-errors
"""LangGraph ReAct 引擎 — 个人助手版。

图结构（架构 v5.0）:
intent_recognize → profile_inject → llm_think → tool_execute → observe
    → check_state → (loop|shard_extract → strategy_search → END|strategy_save → END)

新增节点:
- profile_inject: 意图识别后注入用户画像
- strategy_search: 分片后检索历史策略
"""
import json
import re
from typing import Any

from langgraph.graph import END, StateGraph  # type: ignore[import-untyped]


def _extract_json_block(text: str) -> dict[str, Any] | None:
    match = re.search(r"```json\s*(\{.*?\})\s*```", text, re.DOTALL)
    if not match:
        match = re.search(r"(\{[^{}]*\"action_plan\"[^{}]*\})", text, re.DOTALL)
    if not match:
        match = re.search(r"(\{[^{}]*\"final_answer\"[^{}]*\})", text, re.DOTALL)
    if not match:
        return None
    try:
        return json.loads(match.group(1))
    except (json.JSONDecodeError, IndexError):
        return None


# ---- 节点函数 ----

async def node_intent_recognize(state: dict[str, Any]) -> dict[str, Any]:
    """节点 1: 意图识别。"""
    from app.layers.agent_core.llm_router import llm_router
    from app.layers.agent_core.prompt_engine import prompt_engine

    user_input: str = state.get("user_input", "")
    prompt = prompt_engine.build_intent_classify_prompt(user_input)
    try:
        model = llm_router.select_model("intent_recognition")
        response = await llm_router.call_with_retry(prompt, model)
        content = await llm_router.extract_content(response)
        state["intent"] = content.strip().lower()
    except Exception:
        state["intent"] = "general_qa"
    return state


async def node_profile_inject(state: dict[str, Any]) -> dict[str, Any]:
    """节点 2: 画像注入（新增）。

    架构规则 AR-3: 每次推理前必须注入用户画像。
    从 UserProfileManager 加载画像并注入 Prompt 模板。
    """
    from app.layers.agent_core.user_profile_manager import user_profile_manager

    user_id = state.get("user_id", "")
    if user_id:
        profile = await user_profile_manager.load_profile(user_id)
        user_profile_manager.inject_profile(profile, state)
    else:
        state["profile_context"] = "暂无用户画像（用户未登录）"
        state["user_context"] = {}

    return state


async def node_llm_think(state: dict[str, Any]) -> dict[str, Any]:
    """节点 3: LLM 推理思考。"""
    from app.layers.agent_core.llm_router import llm_router
    from app.layers.agent_core.prompt_engine import prompt_engine
    from app.layers.reasoning.error_handler import error_handler

    # 加载历史 ContextShard（如果还没加载）
    if not state.get("context_shard_info"):
        try:
            from app.layers.agent_core.memory_orchestrator import memory_orchestrator
            from app.models.memory import MemoryType
            task_id = state.get("task_id", "")
            user_id = state.get("user_id", "")
            record = await memory_orchestrator.read(user_id, MemoryType.LONG_TERM, task_id)
            if record and record.data:
                from app.layers.agent_core.context_shard import context_shard_manager
                try:
                    from app.models.context_shard import ContextShard
                    shard = ContextShard(**record.data)
                    state["context_shard_info"] = context_shard_manager.inject_shard(shard, state)
                except Exception:
                    state["context_shard_info"] = "无（首次对话）"
        except Exception:
            pass

    prompt = prompt_engine.build_think_prompt(state)
    max_retries = 3
    for attempt in range(max_retries):
        try:
            model = llm_router.select_model("think")
            response = await llm_router.call_with_retry(prompt, model)
            content = await llm_router.extract_content(response)
            state["think_result"] = content

            parsed = _extract_json_block(content)
            if parsed:
                if "action_plan" in parsed:
                    state["action_plan"] = parsed["action_plan"]
                    state["is_done"] = False
                    break
                elif "final_answer" in parsed:
                    state["final_answer"] = parsed["final_answer"]
                    state["is_done"] = True
                    state["action_plan"] = {}
                    break
            else:
                if attempt < max_retries - 1:
                    continue
                state["action_plan"] = {}
                state["is_done"] = False
                break
        except Exception as e:
            if attempt < max_retries - 1:
                continue
            state = error_handler.format_error_state(state, e)
            state["action_plan"] = {}
    return state


async def node_tool_execute(state: dict[str, Any]) -> dict[str, Any]:
    """节点 4: 工具执行（支持内置工具 + MCP 工具）。"""
    from app.layers.tool.http_executor import http_executor
    from app.layers.tool.result_parser import result_parser
    from app.layers.tool.tool_registry import tool_registry

    action_plan = state.get("action_plan") or {}
    if not action_plan:
        state["observation"] = "no tool to execute"
        return state

    tool_name = action_plan.get("tool", "")
    tool_params = action_plan.get("params", {})
    source_type = action_plan.get("source_type", "unknown")

    # 检查是否为 MCP 工具
    if tool_name.startswith("mcp:"):
        try:
            from app.layers.agent_core.mcp_client import mcp_client
            from app.layers.security.mcp_security import mcp_security_gateway

            user_id = state.get("user_id", "")
            mcp_tool_name = tool_name[4:]  # 去掉 "mcp:" 前缀

            # 安全网关检查
            allowed, sanitized_params, reason = await mcp_security_gateway.gate_call(
                user_id, mcp_tool_name, tool_params,
                user_permissions=state.get("user_permissions", []),
            )
            if not allowed:
                mcp_security_gateway.audit_call(user_id, mcp_tool_name, tool_params, False, reason)
                state["observation"] = f"MCP tool blocked: {reason}"
                return state

            # 执行 MCP 调用
            result = await mcp_client.call_tool(mcp_tool_name, sanitized_params)
            mcp_security_gateway.audit_call(
                user_id, mcp_tool_name, sanitized_params, result.success,
                result.error, result.latency_ms,
            )

            if result.success and result.data:
                content = result.data.get("content", str(result.data))
                state["tool_result"] = result.data
                state["observation"] = content[:2000]  # 截断过长结果
            else:
                state["tool_result"] = None
                state["observation"] = result.error or f"MCP tool {mcp_tool_name} failed"
            return state
        except Exception as e:
            state["observation"] = f"MCP tool execution error: {e}"
            return state

    # 内置工具执行
    try:
        tool_meta = tool_registry.get(tool_name)
    except KeyError:
        state["observation"] = f"Tool not found: {tool_name}"
        return state

    url = tool_params.pop("url", "")
    result = await http_executor.execute_with_retry(tool_name, tool_params, url=url)

    if result.success and result.data:
        parsed = result_parser.parse(
            result.data if isinstance(result.data, dict) else {"raw": str(result.data)},
            source_type,
        )
        state["tool_result"] = parsed.model_dump()
        state["observation"] = parsed.snippet or f"Tool {tool_name} executed successfully"
    else:
        state["tool_result"] = None
        state["observation"] = result.error or f"Tool {tool_name} failed"

    return state


async def node_observe(state: dict[str, Any]) -> dict[str, Any]:
    """节点 5: 观察与反思。"""
    from app.layers.agent_core.llm_router import llm_router
    from app.layers.agent_core.prompt_engine import prompt_engine
    from app.layers.reasoning.decision_reasoning import confidence_scorer

    prompt = prompt_engine.build_observe_prompt(state)
    try:
        model = llm_router.select_model("observe")
        response = await llm_router.call_with_retry(prompt, model)
        content = await llm_router.extract_content(response)
        state["observation"] = content
    except Exception:
        state["observation"] = state.get("observation") or "Observation failed"

    tool_result = state.get("tool_result")
    if tool_result:
        confidence_scorer.score_individual_fact(
            tool_result if isinstance(tool_result, dict) else {"fact": str(tool_result)}
        )

    return state


async def node_check_state(state: dict[str, Any]) -> dict[str, Any]:
    """节点 6: 状态检查与循环控制。"""
    from app.layers.agent_core.context_manager import context_manager
    from app.layers.reasoning.error_handler import error_handler

    messages = state.get("messages", [])
    token_count = context_manager.estimate_tokens(messages)
    state["token_count"] = token_count
    state["context_usage_ratio"] = context_manager.get_context_usage(state)
    state["should_shard"] = context_manager.should_shard(state)

    if error_handler.handle_loop_limit(state):
        state["is_done"] = True
        state["final_answer"] = f"max rounds ({error_handler.MAX_LOOP_COUNT}) reached"
        return state

    loop_count: int = state.get("loop_count", 0)
    state["loop_count"] = loop_count + 1
    return state


async def node_shard_extract(state: dict[str, Any]) -> dict[str, Any]:
    """节点 7: 状态包提取。"""
    from app.layers.agent_core.context_shard import context_shard_manager
    from app.layers.agent_core.memory_orchestrator import memory_orchestrator
    from app.models.memory import MemoryType

    shard = await context_shard_manager.extract_shard(state)
    if shard is not None:
        shard_dict = shard.model_dump()
        state["current_shard"] = shard_dict
        state["shard_saved"] = True
        state["context_shard_info"] = context_shard_manager.inject_shard(shard, state)

        user_id = state.get("user_id", "")
        task_id = state.get("task_id", "")
        try:
            await memory_orchestrator.write_shard(user_id, task_id, shard_dict)
        except Exception:
            try:
                from app.infrastructure.callback_client import callback_client
                await callback_client.save_shard(shard_dict)
            except Exception:
                pass
    else:
        state["shard_saved"] = False
        state["observation"] = "Shard extraction skipped (context usage below threshold)"

    return state


async def node_strategy_search(state: dict[str, Any]) -> dict[str, Any]:
    """节点 8: 策略检索（新增）。

    架构要求在 shard_extract 后检索历史策略，为策略复用提供依据。
    """
    from app.layers.agent_core.strategy_engine import strategy_engine

    intent = state.get("intent", "general_qa")
    task_goal = state.get("user_input", "")
    user_id = state.get("user_id", "")

    try:
        # 检索历史策略
        results = await strategy_engine.search_strategy(
            task_type=intent,
            query_pattern=task_goal[:200],
            limit=5,
        )
        if results:
            decision = strategy_engine.reuse_decision(results)
            state["strategy_decision"] = decision.decision
            state["strategy_similarity"] = decision.similarity
            state["strategy_suggested_sources"] = decision.suggested_sources
            if decision.matched_record:
                state["strategy_matched_id"] = decision.matched_record.strategy_id
        else:
            state["strategy_decision"] = "COLD_START"
            state["strategy_similarity"] = 0.0
    except Exception:
        state["strategy_decision"] = "COLD_START"
        state["strategy_similarity"] = 0.0

    return state


async def node_strategy_save(state: dict[str, Any]) -> dict[str, Any]:
    """节点 9: 策略保存与收尾。"""
    from app.layers.agent_core.strategy_engine import strategy_engine
    from app.layers.agent_core.memory_orchestrator import memory_orchestrator
    from app.models.memory import MemoryType
    from app.models.strategy import SourceCombo, StrategyRecord

    intent = state.get("intent", "general_qa")
    final_answer = state.get("final_answer", "")
    loop_count = state.get("loop_count", 0)
    user_id = state.get("user_id", "")
    task_id = state.get("task_id", "")

    strategy_saved = False
    try:
        default_strategy = strategy_engine.get_default_strategy(intent)
        sources = default_strategy.get("sources", ["web_search"])
        weights = default_strategy.get("weights", {})

        record = StrategyRecord(
            strategy_id=f"strategy-{task_id}-{loop_count}",
            user_id=user_id,
            task_type=intent,
            query_pattern=final_answer[:200] if final_answer else "",
            source_combo=[
                SourceCombo(source=s, weight=weights.get(s, 0.5), reliability=0.7)
                for s in sources
            ],
            success_score=0.5,
            cost_ms=loop_count * 2000,
        )

        try:
            await memory_orchestrator.write_strategy(
                user_id, record.strategy_id, record.model_dump(),
            )
            strategy_saved = True
        except Exception:
            await strategy_engine.save_strategy(record)
            strategy_saved = True
    except Exception:
        strategy_saved = False

    state["strategy_saved"] = strategy_saved
    state["is_done"] = True
    return state


# ---- 路由函数 ----

def _route_after_check(state: dict[str, Any]) -> str:
    """check_state 后的条件路由。

    新版路由:
    - is_done → strategy_save (结束)
    - should_shard → shard_extract → strategy_search → END
    - context_usage < 80% → llm_think (继续循环)
    - context_usage >= 80% → shard_extract (即将超限，先保存)
    """
    if state.get("is_done", False):
        return "node_strategy_save"
    if state.get("should_shard", False):
        return "node_shard_extract"
    ratio: float = state.get("context_usage_ratio", 0)
    if ratio < 0.80:
        return "node_llm_think"
    return "node_shard_extract"


# ---- 图构建 ----

def build_react_graph() -> Any:
    """构建个人助手版 ReAct 图。

    新图结构:
    intent_recognize → profile_inject → llm_think → tool_execute → observe
        → check_state → (loop | shard_extract → strategy_search → END | strategy_save → END)
    """
    workflow: StateGraph = StateGraph(dict)  # type: ignore[type-arg]

    # 注册所有节点
    workflow.add_node("node_intent_recognize", node_intent_recognize)
    workflow.add_node("node_profile_inject", node_profile_inject)
    workflow.add_node("node_llm_think", node_llm_think)
    workflow.add_node("node_tool_execute", node_tool_execute)
    workflow.add_node("node_observe", node_observe)
    workflow.add_node("node_check_state", node_check_state)
    workflow.add_node("node_shard_extract", node_shard_extract)
    workflow.add_node("node_strategy_search", node_strategy_search)
    workflow.add_node("node_strategy_save", node_strategy_save)

    # 设置入口和边
    workflow.set_entry_point("node_intent_recognize")
    workflow.add_edge("node_intent_recognize", "node_profile_inject")
    workflow.add_edge("node_profile_inject", "node_llm_think")
    workflow.add_edge("node_llm_think", "node_tool_execute")
    workflow.add_edge("node_tool_execute", "node_observe")
    workflow.add_edge("node_observe", "node_check_state")

    # 条件路由
    workflow.add_conditional_edges(
        "node_check_state",
        _route_after_check,
        {
            "node_llm_think": "node_llm_think",
            "node_shard_extract": "node_shard_extract",
            "node_strategy_save": "node_strategy_save",
        },
    )

    # 分片后 → 策略检索 → 结束
    workflow.add_edge("node_shard_extract", "node_strategy_search")
    workflow.add_edge("node_strategy_search", END)

    # 策略保存 → 结束
    workflow.add_edge("node_strategy_save", END)

    return workflow.compile()


react_graph = build_react_graph()
