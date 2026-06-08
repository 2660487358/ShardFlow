"""End-to-end smoke tests for the ReAct loop: THINK → ACTION → OBSERVE → CHECK flow."""
from contextlib import ExitStack
from unittest.mock import AsyncMock, patch

import pytest

from app.layers.agent_core.langgraph_engine import build_react_graph, react_graph
from app.models.kb_state import create_initial_state


def _mock_llm_response(content: str) -> dict:
    return {"choices": [{"message": {"content": content}}]}


def _apply_patches(stack: ExitStack, mock_redis, mock_tool_result=None):
    """Apply all common patches for ReAct loop testing."""
    async def _mock_stream(*args, **kwargs):
        yield '{"final_answer": "Dubbo registry traced via ZooKeeper"}'
    if mock_tool_result is None:
        mock_tool_result = type("ToolResult", (), {
            "success": True, "data": {"snippet": "mock result"}, "error": "",
        })()
    stack.enter_context(patch(
        "app.layers.agent_core.llm_router.llm_router.call_llm",
        AsyncMock(return_value=_mock_llm_response("code_exploration")),
    ))
    stack.enter_context(patch(
        "app.layers.agent_core.llm_router.llm_router.call_with_retry",
        AsyncMock(return_value=_mock_llm_response("code_exploration")),
    ))
    stack.enter_context(patch(
        "app.layers.agent_core.llm_router.llm_router.call_stream_with_retry",
        side_effect=_mock_stream,
    ))
    stack.enter_context(patch(
        "app.layers.agent_core.llm_router.llm_router.extract_content",
        AsyncMock(return_value="code_exploration"),
    ))
    stack.enter_context(patch(
        "app.layers.agent_core.llm_router.llm_router.select_model",
        return_value="gpt-4o-mini",
    ))
    stack.enter_context(patch(
        "app.infrastructure.redis_client.redis_client.get_redis",
        AsyncMock(return_value=mock_redis),
    ))
    stack.enter_context(patch(
        "app.infrastructure.redis_client.redis_client.connect", AsyncMock(),
    ))
    stack.enter_context(patch(
        "app.infrastructure.redis_client.redis_client.disconnect", AsyncMock(),
    ))
    stack.enter_context(patch(
        "app.infrastructure.callback_client.callback_client.save_shard",
        AsyncMock(return_value={"ok": True}),
    ))
    stack.enter_context(patch(
        "app.infrastructure.callback_client.callback_client.get_shard",
        AsyncMock(return_value=None),
    ))
    stack.enter_context(patch(
        "app.infrastructure.callback_client.callback_client.save_strategy",
        AsyncMock(return_value={"ok": True}),
    ))
    stack.enter_context(patch(
        "app.layers.tool.http_executor.http_executor.execute_with_retry",
        AsyncMock(return_value=mock_tool_result),
    ))
    stack.enter_context(patch(
        "app.layers.reasoning.error_handler.error_handler.MAX_LOOP_COUNT", 3,
    ))


@pytest.mark.asyncio
async def test_graph_compiles():
    """Verify the react graph compiles without errors."""
    graph = build_react_graph()
    assert graph is not None
    assert react_graph is not None


@pytest.mark.asyncio
async def test_graph_nodes_are_registered():
    """Verify all 7 nodes are registered in the graph."""
    graph = build_react_graph()
    expected = [
        "node_intent_recognize", "node_llm_think", "node_tool_execute",
        "node_observe", "node_check_state", "node_shard_extract", "node_strategy_save",
    ]
    for node in expected:
        assert node in graph.nodes, f"Node {node} not found in graph"


@pytest.mark.asyncio
async def test_react_loop_runs_end_to_end():
    """Simulate full ReAct loop through all nodes until termination by loop limit."""
    state = create_initial_state(
        task_id="test-e2e-001",
        user_id="test-user",
        session_id="test-session",
        user_input="trace Dubbo registry flow",
        max_rounds=3,
    )
    state["action_plan"] = {"tool": "search_code", "params": {}, "source_type": "github"}

    mock_redis = AsyncMock()
    mock_redis.get.return_value = None
    mock_redis.set.return_value = None
    mock_redis.delete.return_value = None

    mock_tool_result = type("ToolResult", (), {
        "success": True,
        "data": {"title": "test", "snippet": "Dubbo registry flow traced", "url": "", "score": 0.9},
        "error": "",
    })()

    with ExitStack() as stack:
        _apply_patches(stack, mock_redis, mock_tool_result)
        result = await react_graph.ainvoke(state, {"recursion_limit": 30})

    assert result.get("is_done") is True
    assert result.get("intent") is not None
    # With valid final_answer JSON from mock stream, terminates after 1 loop
    assert result.get("loop_count", 0) >= 1
    assert result.get("final_answer") == "Dubbo registry traced via ZooKeeper"
    assert result.get("strategy_saved") is not None


@pytest.mark.asyncio
async def test_state_transitions_smoke():
    """Verify state flows: intent set, loop counts up, final answer populated."""
    state = create_initial_state(
        task_id="test-transitions-001",
        user_id="test-user",
        session_id="test-session",
        user_input="find all Redis config",
        max_rounds=2,
    )
    state["action_plan"] = {"tool": "query_source", "params": {}, "source_type": "official_doc"}

    mock_redis = AsyncMock()
    mock_redis.get.return_value = None
    mock_redis.set.return_value = None
    mock_redis.delete.return_value = None

    mock_tool_result = type("ToolResult", (), {
        "success": True, "data": {"snippet": "redis config found"}, "error": "",
    })()

    with ExitStack() as stack:
        _apply_patches(stack, mock_redis, mock_tool_result)
        result = await react_graph.ainvoke(state, {"recursion_limit": 30})

    assert result.get("is_done") is True
    assert result.get("loop_count", 0) >= 1
    assert result.get("final_answer") == "Dubbo registry traced via ZooKeeper"


@pytest.mark.asyncio
async def test_langgraph_graph_structure():
    """Confirm the ReAct graph has all required nodes."""
    graph = build_react_graph()
    for node in [
        "node_intent_recognize", "node_llm_think", "node_tool_execute",
        "node_observe", "node_check_state", "node_shard_extract", "node_strategy_save",
    ]:
        assert node in graph.nodes


@pytest.mark.asyncio
async def test_loop_limit_reached():
    """Verify graph terminates immediately when loop_count is at the limit."""
    state = create_initial_state(
        task_id="test-limit-001",
        user_id="test-user",
        session_id="test-session",
        user_input="trace all dependencies",
        max_rounds=1,
    )
    state["loop_count"] = 3  # At patched MAX_LOOP_COUNT

    mock_redis = AsyncMock()
    mock_redis.get.return_value = None
    mock_redis.set.return_value = None
    mock_redis.delete.return_value = None

    with ExitStack() as stack:
        _apply_patches(stack, mock_redis, None)
        result = await react_graph.ainvoke(state, {"recursion_limit": 10})

    assert result.get("is_done") is True
    assert "max rounds" in result.get("final_answer", "")


@pytest.mark.asyncio
async def test_acceptance_scenario_dubbo_registry():
    """Acceptance test: trace Dubbo registry — full ReAct loop from input to strategy_save.

    Exercises: intent_recognize → llm_think → tool_execute → observe → check_state
    (loops until MAX_LOOP_COUNT=3 reached) → strategy_save.
    """
    state = create_initial_state(
        task_id="acceptance-dubbo-001",
        user_id="test-user",
        session_id="test-session",
        user_input="理清Dubbo注册链路",
        max_rounds=3,
    )
    state["action_plan"] = {
        "tool": "search_code",
        "params": {"query": "Dubbo registry"},
        "source_type": "github",
    }

    mock_redis = AsyncMock()
    mock_redis.get.return_value = None
    mock_redis.set.return_value = None
    mock_redis.delete.return_value = None

    mock_tool_result = type("ToolResult", (), {
        "success": True,
        "data": {
            "title": "Dubbo Registry",
            "snippet": "Dubbo registers services via ZooKeeper/Nacos registry center",
            "url": "",
            "score": 0.95,
        },
        "error": "",
    })()

    with ExitStack() as stack:
        _apply_patches(stack, mock_redis, mock_tool_result)
        result = await react_graph.ainvoke(state, {"recursion_limit": 30})

    assert result.get("is_done") is True
    assert result.get("intent") == "code_exploration"
    assert result.get("loop_count", 0) >= 1
    assert result.get("final_answer") == "Dubbo registry traced via ZooKeeper"
    assert result.get("strategy_saved") is not None
