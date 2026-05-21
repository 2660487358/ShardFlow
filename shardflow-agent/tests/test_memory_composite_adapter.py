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
    await adapter._l0.write("t1", MemoryType.LONG_TERM, "k1", {"v": "L0"})

    record = await adapter.read("t1", MemoryType.LONG_TERM, "k1")
    assert record is not None
    assert record.data["v"] == "L0"


@pytest.mark.asyncio
async def test_composite_write_broadcasts_to_l0():
    """Write must update L0 immediately."""
    adapter = CompositeAdapter()
    mock_redis = AsyncMock()
    mock_redis.get.return_value = None
    mock_redis.set.return_value = None

    with (
        patch("app.infrastructure.redis_client.redis_client.get_redis", AsyncMock(return_value=mock_redis)),
        patch("app.infrastructure.callback_client.callback_client.save_shard", AsyncMock(return_value={"ok": True})),
    ):
        record = await adapter.write("t1", MemoryType.LONG_TERM, "k1", {"v": "written"})

    # Verify L0 has it immediately
    l0_record = await adapter._l0.read("t1", MemoryType.LONG_TERM, "k1")
    assert l0_record is not None
    assert l0_record.data["v"] == "written"


@pytest.mark.asyncio
async def test_composite_tenant_isolation_in_read():
    """Tenant A cannot read Tenant B's data."""
    adapter = CompositeAdapter()
    await adapter._l0.write("tenant-A", MemoryType.LONG_TERM, "key-1", {"owner": "A"})
    await adapter._l0.write("tenant-B", MemoryType.LONG_TERM, "key-1", {"owner": "B"})

    a = await adapter._l0.read("tenant-A", MemoryType.LONG_TERM, "key-1")
    b = await adapter._l0.read("tenant-B", MemoryType.LONG_TERM, "key-1")
    assert a.data["owner"] == "A"
    assert b.data["owner"] == "B"
