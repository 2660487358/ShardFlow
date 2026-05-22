"""Phase 3.2: L0CacheAdapter unit tests — read/write/delete/exists."""
import pytest
from app.models.memory import MemoryType
from app.layers.agent_core.memory_adapters.l0_adapter import L0CacheAdapter


@pytest.mark.asyncio
async def test_l0_write_and_read():
    adapter = L0CacheAdapter()
    record = await adapter.write("user-1", MemoryType.LONG_TERM, "task-1",
                                  {"fact": "Dubbo uses ZooKeeper"})
    assert record.key == "task-1"
    assert record.data["fact"] == "Dubbo uses ZooKeeper"

    found = await adapter.read("user-1", MemoryType.LONG_TERM, "task-1")
    assert found is not None
    assert found.data["fact"] == "Dubbo uses ZooKeeper"


@pytest.mark.asyncio
async def test_l0_read_missing():
    adapter = L0CacheAdapter()
    found = await adapter.read("user-1", MemoryType.LONG_TERM, "nonexistent")
    assert found is None


@pytest.mark.asyncio
async def test_l0_delete():
    adapter = L0CacheAdapter()
    await adapter.write("u1", MemoryType.SHORT_TERM, "session-1", {"msg": "hi"})
    assert await adapter.exists("u1", MemoryType.SHORT_TERM, "session-1")

    deleted = await adapter.delete("u1", MemoryType.SHORT_TERM, "session-1")
    assert deleted is True
    assert not await adapter.exists("u1", MemoryType.SHORT_TERM, "session-1")


@pytest.mark.asyncio
async def test_l0_user_isolation():
    adapter = L0CacheAdapter()
    await adapter.write("user-A", MemoryType.LONG_TERM, "task-1", {"data": "A"})
    await adapter.write("user-B", MemoryType.LONG_TERM, "task-1", {"data": "B"})

    a = await adapter.read("user-A", MemoryType.LONG_TERM, "task-1")
    b = await adapter.read("user-B", MemoryType.LONG_TERM, "task-1")
    assert a is not None and a.data["data"] == "A"
    assert b is not None and b.data["data"] == "B"
