"""MemoryStore Protocol — the unified abstraction for all memory backends.

Per AGENT_LAYER_MODEL.md L2 requirement:
    "记忆接口层：定义记忆读写的抽象接口，屏蔽底层存储差异。关键技术：抽象工厂、依赖注入。"

Uses typing.Protocol (structural subtyping) rather than ABC to minimize runtime overhead.
All methods are async because every backend involves I/O (even L0 might be shared-memory in future).
"""
from typing import Any, Protocol, runtime_checkable

from app.models.memory import MemoryRecord, MemoryQuery, MemoryType


@runtime_checkable
class MemoryStore(Protocol):
    """Unified async interface for memory read/write/delete/search/exists.

    Every adapter (L0Cache, Redis, JavaAPI, Composite) implements this Protocol.
    Upper-layer code interacts ONLY through this interface, never with concrete adapters.
    """

    async def read(self, tenant_id: str, memory_type: MemoryType, key: str) -> MemoryRecord | None:
        """Read a single memory record by key.

        Returns None if the key does not exist or has expired.
        Must be tenant-isolated: tenant_id is always provided and MUST be used
        to scope the read (adapter prefixes keys with tenant_id).
        """
        ...

    async def write(self, tenant_id: str, memory_type: MemoryType, key: str,
                    data: dict[str, Any], ttl_seconds: int = 0) -> MemoryRecord:
        """Write (create or update) a memory record.

        Returns the written MemoryRecord with version and timestamps populated.
        Implementations should handle idempotency: writing the same key+data
        multiple times produces the same result.
        """
        ...

    async def delete(self, tenant_id: str, memory_type: MemoryType, key: str) -> bool:
        """Delete a memory record. Returns True if deleted, False if not found."""
        ...

    async def search(self, tenant_id: str, memory_type: MemoryType,
                     query: MemoryQuery) -> list[MemoryRecord]:
        """Search memory records matching query filters.

        Returns up to query.limit records sorted by updated_at descending.
        """
        ...

    async def exists(self, tenant_id: str, memory_type: MemoryType, key: str) -> bool:
        """Check if a memory record exists (without retrieving full data)."""
        ...


class MemoryStoreFactory(Protocol):
    """Abstract factory for creating MemoryStore instances.

    Allows DI containers to inject the right adapter based on memory_type
    without upper layers knowing the concrete implementation.
    """

    def create(self, memory_type: MemoryType) -> MemoryStore:
        """Create and return a MemoryStore adapter for the given memory type."""
        ...
