"""Phase 3.6: MemoryOrchestrator unit tests — routing by MemoryType, unified API."""
from unittest.mock import AsyncMock, patch
import pytest
from app.models.memory import MemoryType, MemoryQuery
from app.layers.agent_core.memory_orchestrator import MemoryOrchestrator


@pytest.mark.asyncio
async def test_orchestrator_write_and_read_long_term():
    orchestrator = MemoryOrchestrator()
    mock_redis = AsyncMock()
    mock_redis.get.return_value = None
    mock_redis.set.return_value = None
    mock_redis.delete.return_value = 0

    with (
        patch("app.infrastructure.redis_client.redis_client.get_redis", AsyncMock(return_value=mock_redis)),
        patch("app.infrastructure.redis_client.redis_client.connect", AsyncMock()),
        patch("app.infrastructure.redis_client.redis_client.disconnect", AsyncMock()),
        patch("app.infrastructure.callback_client.callback_client.save_shard", AsyncMock(return_value={"ok": True})),
        patch("app.infrastructure.callback_client.callback_client.get_shard", AsyncMock(return_value=None)),
    ):
        record = await orchestrator.write("t1", MemoryType.LONG_TERM, "task-1",
                                           {"fact": "test"})
        assert record.key == "task-1"
        assert record.memory_type == MemoryType.LONG_TERM


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
        patch("app.infrastructure.callback_client.callback_client.save_shard", AsyncMock(return_value={"ok": True})),
        patch("app.infrastructure.callback_client.callback_client.save_strategy", AsyncMock(return_value={"ok": True})),
    ):
        shard_record = await orchestrator.write_shard("t1", "task-1", {"version": 1})
        assert shard_record.memory_type == MemoryType.LONG_TERM

        strategy_record = await orchestrator.write_strategy("t1", "strat-1", {"strategy_id": "strat-1"})
        assert strategy_record.memory_type == MemoryType.META

        session_record = await orchestrator.write_session("t1", "session-1", {"messages": []})
        assert session_record.memory_type == MemoryType.SHORT_TERM


@pytest.mark.asyncio
async def test_orchestrator_separate_adapters_per_type():
    """Verify SHORT_TERM, LONG_TERM, and META use separate CompositeAdapter instances."""
    orchestrator = MemoryOrchestrator()
    assert orchestrator._short_term is not orchestrator._long_term
    assert orchestrator._long_term is not orchestrator._meta
    assert orchestrator._short_term is not orchestrator._meta
