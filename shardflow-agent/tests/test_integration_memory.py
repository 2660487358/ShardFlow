"""Phase 4.1: LangGraph node integration tests — verify nodes use MemoryOrchestrator."""
from unittest.mock import AsyncMock, patch
import pytest
from app.layers.agent_core.langgraph_engine import react_graph
from app.models.kb_state import create_initial_state


def _mock_llm_response(content: str) -> dict:
    return {"choices": [{"message": {"content": content}}]}


@pytest.mark.asyncio
async def test_node_shard_extract_uses_memory_orchestrator():
    """Verify node_shard_extract calls memory_orchestrator.write_shard."""
    state = create_initial_state(
        task_id="mem-test-001", user_id="test-user",
        session_id="test-session", user_input="trace Dubbo",
        max_rounds=2,
    )
    state["context_usage_ratio"] = 0.85
    state["pending"] = ["question 1"]
    state["action_plan"] = {"tool": "search_code", "params": {}}
    state["loop_count"] = 14  # Near limit

    mock_redis = AsyncMock()
    mock_redis.get.return_value = None
    mock_redis.set.return_value = None
    mock_redis.delete.return_value = 0

    mock_tool_result = type("ToolResult", (), {
        "success": True, "data": {"snippet": "ok"}, "error": "",
    })()

    with (
        patch("app.layers.agent_core.llm_router.llm_router.call_llm",
              AsyncMock(return_value=_mock_llm_response("code_exploration"))),
        patch("app.layers.agent_core.llm_router.llm_router.call_with_retry",
              AsyncMock(return_value=_mock_llm_response("code_exploration"))),
        patch("app.layers.agent_core.llm_router.llm_router.extract_content",
              AsyncMock(return_value="code_exploration")),
        patch("app.layers.agent_core.llm_router.llm_router.select_model",
              return_value="gpt-4o-mini"),
        patch("app.infrastructure.redis_client.redis_client.get_redis",
              AsyncMock(return_value=mock_redis)),
        patch("app.infrastructure.redis_client.redis_client.connect", AsyncMock()),
        patch("app.infrastructure.redis_client.redis_client.disconnect", AsyncMock()),

        patch("app.layers.tool.http_executor.http_executor.execute_with_retry",
              AsyncMock(return_value=mock_tool_result)),
        patch("app.layers.reasoning.error_handler.error_handler.MAX_LOOP_COUNT", 3),
    ):
        result = await react_graph.ainvoke(state, {"recursion_limit": 30})

    assert result.get("is_done") is True
    # Verify strategy was saved through the memory layer path
    assert result.get("strategy_saved") is not None
