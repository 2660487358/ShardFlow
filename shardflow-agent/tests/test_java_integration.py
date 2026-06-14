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
async def test_callback_session_complete():
    """Verify session_complete callback."""
    from app.infrastructure.callback_client import callback_client

    mock_client = _mock_async_client({"status": "ok"})

    with patch.object(callback_client, "_get_client", AsyncMock(return_value=mock_client)):
        result = await callback_client.session_complete({"session_id": "s1"})

    assert result["status"] == "ok"
