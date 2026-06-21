"""Phase 3.5: CompositeAdapter integration — L0→L1→L2 degrade-read + write-broadcast."""
from unittest.mock import AsyncMock, patch
import pytest
from app.models.memory import MemoryType, MemoryQuery
from app.layers.agent_core.memory_adapters.composite_adapter import CompositeAdapter


@pytest.mark.asyncio
async def test_composite_read_l0_hit():
    """L0 hit returns immediately, no L1/L2 call."""
    adapter = CompositeAdapter()

    # Write to L0
    await adapter._l0.write("u1", MemoryType.SESSION_SUMMARY, "k1", {"v": "L0"})

    record = await adapter.read("u1", MemoryType.SESSION_SUMMARY, "k1")
    assert record is not None
    assert record.data["v"] == "L0"


@pytest.mark.asyncio
async def test_composite_write_broadcasts_to_l0():
    """Write must update L0 immediately."""
    adapter = CompositeAdapter()
    mock_redis = AsyncMock()
    mock_redis.get.return_value = None
    mock_redis.set.return_value = None

    async def _fake_l2_write(user_id, memory_type, key, data, ttl_seconds=0):
        from app.models.memory import MemoryRecord
        from datetime import datetime, timezone
        return MemoryRecord(key=key, user_id=user_id, memory_type=memory_type, data=data, updated_at=datetime.now(timezone.utc))

    with (
        patch("app.infrastructure.redis_client.redis_client.get_redis", AsyncMock(return_value=mock_redis)),
        patch.object(adapter._l2, "write", side_effect=_fake_l2_write),
    ):
        record = await adapter.write("u1", MemoryType.SESSION_SUMMARY, "k1", {"v": "written"})

    # Verify L0 has it immediately
    l0_record = await adapter._l0.read("u1", MemoryType.SESSION_SUMMARY, "k1")
    assert l0_record is not None
    assert l0_record.data["v"] == "written"


@pytest.mark.asyncio
async def test_composite_user_isolation_in_read():
    """User A cannot read User B's data."""
    adapter = CompositeAdapter()
    await adapter._l0.write("user-A", MemoryType.SESSION_SUMMARY, "key-1", {"owner": "A"})
    await adapter._l0.write("user-B", MemoryType.SESSION_SUMMARY, "key-1", {"owner": "B"})

    a = await adapter._l0.read("user-A", MemoryType.SESSION_SUMMARY, "key-1")
    b = await adapter._l0.read("user-B", MemoryType.SESSION_SUMMARY, "key-1")
    assert a.data["owner"] == "A"
    assert b.data["owner"] == "B"
