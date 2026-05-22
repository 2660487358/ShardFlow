"""Phase 2: Python-Java integration tests for callback and proxy interfaces."""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


def _mock_response(json_body: dict) -> MagicMock:
    """Create a mock httpx.Response that returns sync json/raise_for_status."""
    resp = MagicMock()
    resp.json.return_value = json_body
    resp.raise_for_status.return_value = None
    return resp


def _mock_async_client(response_body: dict) -> AsyncMock:
    """Create an AsyncMock httpx.AsyncClient whose post/get return the given response."""
    client = AsyncMock()
    resp = _mock_response(response_body)
    client.post.return_value = resp
    client.get.return_value = resp
    return client


@pytest.mark.asyncio
async def test_callback_save_shard_integration():
    """Verify callback_client.save_shard calls Java kb-callback endpoint."""
    from app.infrastructure.callback_client import callback_client

    mock_client = _mock_async_client({"status": "ok", "shard_id": "test-shard-1"})

    shard_data = {
        "task_id": "test-task-001",
        "user_id": "test-user",
        "session_seq": 1,
        "confirmed": [], "excluded": [], "pending": [],
    }

    with patch.object(callback_client, "_get_client", AsyncMock(return_value=mock_client)):
        result = await callback_client.save_shard(shard_data)

    assert result["status"] == "ok"


@pytest.mark.asyncio
async def test_callback_save_strategy_integration():
    """Verify callback_client.save_strategy calls Java kb-strategy endpoint."""
    from app.infrastructure.callback_client import callback_client

    mock_client = _mock_async_client({"status": "ok"})

    with patch.object(callback_client, "_get_client", AsyncMock(return_value=mock_client)):
        result = await callback_client.save_strategy({"strategy_id": "strat-1"})

    assert result["status"] == "ok"


@pytest.mark.asyncio
async def test_callback_search_strategies_integration():
    """Verify callback_client.search_strategies calls Java kb-strategy search."""
    from app.infrastructure.callback_client import callback_client

    mock_client = _mock_async_client({
        "results": [
            {"record": {"strategy_id": "s1", "task_type": "code_exploration"}, "similarity": 0.95}
        ]
    })

    with patch.object(callback_client, "_get_client", AsyncMock(return_value=mock_client)):
        results = await callback_client.search_strategies("code_exploration", "trace dubbo")

    assert len(results) == 1
    assert results[0]["similarity"] == 0.95


@pytest.mark.asyncio
async def test_callback_graceful_degradation():
    """Verify strategy search falls back to local cache when Java unavailable."""
    from app.layers.agent_core.strategy_engine import strategy_engine
    from app.models.strategy import SourceCombo, StrategyRecord

    strategy_engine._local_cache = [
        StrategyRecord(
            strategy_id="local-1", user_id="test", task_type="code_exploration",
            query_pattern="trace dubbo",
            source_combo=[SourceCombo(source="code_comments", weight=0.5, reliability=0.7)],
            success_score=0.8, cost_ms=2000,
        )
    ]

    with patch("app.infrastructure.callback_client.callback_client.search_strategies",
               AsyncMock(side_effect=ConnectionError("Java service down"))):
        results = await strategy_engine.search_strategy("code_exploration", "trace dubbo")

    assert len(results) > 0
    assert results[0][0].strategy_id == "local-1"


@pytest.mark.asyncio
async def test_callback_session_complete():
    """Verify session_complete callback."""
    from app.infrastructure.callback_client import callback_client

    mock_client = _mock_async_client({"status": "ok"})

    with patch.object(callback_client, "_get_client", AsyncMock(return_value=mock_client)):
        result = await callback_client.session_complete({"session_id": "s1"})

    assert result["status"] == "ok"
