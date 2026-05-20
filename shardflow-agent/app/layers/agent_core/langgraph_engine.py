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
    action_plan = state.get("action_plan", {})
    if not action_plan:
        state["observation"] = "no tool to execute (stub: tool registry not yet integrated)"
        return state
    tool_name = action_plan.get("tool", "unknown")
    state["observation"] = f"[Stub] Tool {tool_name} executed (Task 5 integration pending)"
    return state


async def node_observe(state: dict[str, Any]) -> dict[str, Any]:
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
    state["observation"] = "[Stub] shard extraction triggered (Task 4 integration pending)"
    return state


async def node_strategy_save(state: dict[str, Any]) -> dict[str, Any]:
    state["observation"] = "[Stub] strategy save triggered (Task 7 integration pending)"
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
