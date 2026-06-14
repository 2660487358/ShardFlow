"""Phase 3.6: MemoryOrchestrator unit tests — routing by MemoryType, unified API."""
from unittest.mock import AsyncMock, patch
import pytest
from app.models.memory import MemoryType, MemoryQuery
from app.layers.agent_core.memory_orchestrator import MemoryOrchestrator


@pytest.mark.asyncio
async def test_orchestrator_write_and_read_session_summary():
    orchestrator = MemoryOrchestrator()
    mock_redis = AsyncMock()
    mock_redis.get.return_value = None
    mock_redis.set.return_value = None
    mock_redis.delete.return_value = 0

    with (
        patch("app.infrastructure.redis_client.redis_client.get_redis", AsyncMock(return_value=mock_redis)),
        patch("app.infrastructure.redis_client.redis_client.connect", AsyncMock()),
        patch("app.infrastructure.redis_client.redis_client.disconnect", AsyncMock()),

    ):
        record = await orchestrator.write("t1", MemoryType.SESSION_SUMMARY, "task-1",
                                           {"fact": "test"})
        assert record.key == "task-1"
        assert record.memory_type == MemoryType.SESSION_SUMMARY


@pytest.mark.asyncio
async def test_orchestrator_convenience_methods():
    orchestrator = MemoryOrchestrator()
    mock_redis = AsyncMock()
    mock_redis.get.return_value = None
    mock_redis.set.return_value = None

    with (
        patch("app.infrastructure.redis_client.redis_client.get_redis", AsyncMock(return_value=mock_redis)),
        patch("app.infrastructure.redis_client.redis_client.connect", AsyncMock()),
        patch("app.infrastructure.redis_client.redis_client.disconnect", AsyncMock()),

    ):
        summary_record = await orchestrator.write_summary("t1", "task-1", {"version": 1})
        assert summary_record.memory_type == MemoryType.SESSION_SUMMARY

        semantic_record = await orchestrator.write_semantic("t1", "sem-1", {"fact": "test"})
        assert semantic_record.memory_type == MemoryType.SEMANTIC

        session_record = await orchestrator.write_session("t1", "session-1", {"messages": []})
        assert session_record.memory_type == MemoryType.SHORT_TERM


@pytest.mark.asyncio
async def test_orchestrator_separate_adapters_per_type():
    """Verify SHORT_TERM, SESSION_SUMMARY, SEMANTIC, and EPISODIC use separate CompositeAdapter instances."""
    orchestrator = MemoryOrchestrator()
    assert orchestrator._short_term is not orchestrator._session_summary
    assert orchestrator._session_summary is not orchestrator._semantic
    assert orchestrator._semantic is not orchestrator._episodic
    assert orchestrator._short_term is not orchestrator._episodic
