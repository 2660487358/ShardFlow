# mypy: ignore-errors
from typing import Any

from langgraph.graph import END, StateGraph  # type: ignore[import-untyped]


async def node_intent_recognize(state: dict[str, Any]) -> dict[str, Any]:
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


async def node_llm_think(state: dict[str, Any]) -> dict[str, Any]:
    from app.layers.agent_core.llm_router import llm_router
    from app.layers.agent_core.prompt_engine import prompt_engine
    from app.layers.reasoning.error_handler import error_handler

    # Read context shard info through MemoryOrchestrator (new path)
    # Falls back to state["context_shard_info"] if orchestrator unavailable
    if not state.get("context_shard_info"):
        try:
            from app.layers.agent_core.memory_orchestrator import memory_orchestrator
            from app.models.memory import MemoryType
            task_id = state.get("task_id", "")
            tenant_id = state.get("tenant_id", "")
            record = await memory_orchestrator.read(tenant_id, MemoryType.LONG_TERM, task_id)
            if record and record.data:
                from app.layers.agent_core.context_shard import context_shard_manager
                try:
                    from app.models.context_shard import ContextShard
                    shard = ContextShard(**record.data)
                    state["context_shard_info"] = context_shard_manager.inject_shard(shard, state)
                except Exception:
                    state["context_shard_info"] = "无（首次探索）"
        except Exception:
            pass

    prompt = prompt_engine.build_think_prompt(state)
    try:
        model = llm_router.select_model("think")
        response = await llm_router.call_with_retry(prompt, model)
        content = await llm_router.extract_content(response)
        state["think_result"] = content
    except Exception as e:
        state = error_handler.format_error_state(state, e)
    return state


async def node_tool_execute(state: dict[str, Any]) -> dict[str, Any]:
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

    try:
        tool_meta = tool_registry.get(tool_name)
    except KeyError:
        state["observation"] = f"Tool not found: {tool_name}"
        return state

    url = tool_params.pop("url", "")
    result = await http_executor.execute_with_retry(tool_name, tool_params, url=url)

    if result.success and result.data:
        parsed = result_parser.parse(result.data if isinstance(result.data, dict) else {"raw": str(result.data)}, source_type)
        state["tool_result"] = parsed.model_dump()
        state["observation"] = parsed.snippet or f"Tool {tool_name} executed successfully"
    else:
        state["tool_result"] = None
        state["observation"] = result.error or f"Tool {tool_name} failed"

    return state


async def node_observe(state: dict[str, Any]) -> dict[str, Any]:
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
        confidence_scorer.score_individual_fact(tool_result if isinstance(tool_result, dict) else {"fact": str(tool_result)})

    return state


async def node_check_state(state: dict[str, Any]) -> dict[str, Any]:
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
    from app.layers.agent_core.context_shard import context_shard_manager
    from app.layers.agent_core.memory_orchestrator import memory_orchestrator
    from app.models.memory import MemoryType

    shard = await context_shard_manager.extract_shard(state)
    if shard is not None:
        shard_dict = shard.model_dump()
        state["current_shard"] = shard_dict
        state["shard_saved"] = True
        state["context_shard_info"] = context_shard_manager.inject_shard(shard, state)

        # Write through MemoryOrchestrator (new unified path)
        tenant_id = state.get("tenant_id", "")
        task_id = state.get("task_id", "")
        try:
            await memory_orchestrator.write_shard(tenant_id, task_id, shard_dict)
        except Exception:
            # Fallback: direct callback
            try:
                from app.infrastructure.callback_client import callback_client
                await callback_client.save_shard(shard_dict)
            except Exception:
                pass
    else:
        state["shard_saved"] = False
        state["observation"] = "Shard extraction skipped (context usage below threshold)"

    return state


async def node_strategy_save(state: dict[str, Any]) -> dict[str, Any]:
    from app.layers.agent_core.strategy_engine import strategy_engine
    from app.layers.agent_core.memory_orchestrator import memory_orchestrator
    from app.models.memory import MemoryType
    from app.models.strategy import SourceCombo, StrategyRecord

    intent = state.get("intent", "general_code_exploration")
    final_answer = state.get("final_answer", "")
    loop_count = state.get("loop_count", 0)
    tenant_id = state.get("tenant_id", "")
    task_id = state.get("task_id", "")

    strategy_saved = False
    try:
        default_strategy = strategy_engine.get_default_strategy(intent)
        sources = default_strategy.get("sources", ["code_comments"])
        weights = default_strategy.get("weights", {})

        record = StrategyRecord(
            strategy_id=f"strategy-{task_id}-{loop_count}",
            tenant_id=tenant_id,
            task_type=intent,
            query_pattern=final_answer[:200] if final_answer else "",
            source_combo=[
                SourceCombo(source=s, weight=weights.get(s, 0.5), reliability=0.7)
                for s in sources
            ],
            success_score=0.5,
            cost_ms=loop_count * 2000,
        )

        # Write through MemoryOrchestrator (new unified path)
        try:
            await memory_orchestrator.write_strategy(
                tenant_id, record.strategy_id, record.model_dump(),
            )
            strategy_saved = True
        except Exception:
            # Fallback: direct strategy_engine save
            await strategy_engine.save_strategy(record)
            strategy_saved = True
    except Exception:
        strategy_saved = False

    state["strategy_saved"] = strategy_saved
    state["is_done"] = True
    return state


def _route_after_check(state: dict[str, Any]) -> str:
    if state.get("is_done", False):
        return "node_strategy_save"
    if state.get("should_shard", False):
        return "node_shard_extract"
    ratio: float = state.get("context_usage_ratio", 0)
    if ratio < 0.80:
        return "node_llm_think"
    return "node_shard_extract"


def build_react_graph() -> Any:
    workflow: StateGraph = StateGraph(dict)  # type: ignore[type-arg]

    workflow.add_node("node_intent_recognize", node_intent_recognize)
    workflow.add_node("node_llm_think", node_llm_think)
    workflow.add_node("node_tool_execute", node_tool_execute)
    workflow.add_node("node_observe", node_observe)
    workflow.add_node("node_check_state", node_check_state)
    workflow.add_node("node_shard_extract", node_shard_extract)
    workflow.add_node("node_strategy_save", node_strategy_save)

    workflow.set_entry_point("node_intent_recognize")
    workflow.add_edge("node_intent_recognize", "node_llm_think")
    workflow.add_edge("node_llm_think", "node_tool_execute")
    workflow.add_edge("node_tool_execute", "node_observe")
    workflow.add_edge("node_observe", "node_check_state")

    workflow.add_conditional_edges(
        "node_check_state",
        _route_after_check,
        {
            "node_llm_think": "node_llm_think",
            "node_shard_extract": "node_shard_extract",
            "node_strategy_save": "node_strategy_save",
        },
    )
    workflow.add_edge("node_shard_extract", "node_strategy_save")
    workflow.add_edge("node_strategy_save", END)

    return workflow.compile()


react_graph = build_react_graph()
