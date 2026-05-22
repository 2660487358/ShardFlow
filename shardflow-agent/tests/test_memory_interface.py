"""Phase 3.1: MemoryStore interface compliance tests.

Verifies all adapters satisfy the MemoryStore Protocol signatures.
"""
import pytest
from app.models.memory import MemoryType, MemoryRecord, MemoryQuery
from app.layers.agent_core.memory_adapters.l0_adapter import L0CacheAdapter
from app.layers.agent_core.memory_adapters.redis_adapter import RedisAdapter
from app.layers.agent_core.memory_adapters.java_adapter import JavaAPIAdapter
from app.layers.agent_core.memory_adapters.composite_adapter import CompositeAdapter


class TestMemoryStoreProtocolCompliance:
    """Verify each adapter has the 5 required MemoryStore methods."""

    REQUIRED_METHODS = ["read", "write", "delete", "search", "exists"]

    def test_l0_adapter_has_all_methods(self):
        adapter = L0CacheAdapter()
        for method in self.REQUIRED_METHODS:
            assert hasattr(adapter, method), f"L0CacheAdapter missing {method}"
            assert callable(getattr(adapter, method)), f"L0CacheAdapter.{method} not callable"

    def test_redis_adapter_has_all_methods(self):
        adapter = RedisAdapter()
        for method in self.REQUIRED_METHODS:
            assert hasattr(adapter, method), f"RedisAdapter missing {method}"
            assert callable(getattr(adapter, method)), f"RedisAdapter.{method} not callable"

    def test_java_adapter_has_all_methods(self):
        adapter = JavaAPIAdapter()
        for method in self.REQUIRED_METHODS:
            assert hasattr(adapter, method), f"JavaAPIAdapter missing {method}"
            assert callable(getattr(adapter, method)), f"JavaAPIAdapter.{method} not callable"

    def test_composite_adapter_has_all_methods(self):
        adapter = CompositeAdapter()
        for method in self.REQUIRED_METHODS:
            assert hasattr(adapter, method), f"CompositeAdapter missing {method}"
            assert callable(getattr(adapter, method)), f"CompositeAdapter.{method} not callable"


class TestMemoryModels:
    """Verify memory type system models."""

    def test_memory_type_enum(self):
        assert MemoryType.SHORT_TERM.value == "short_term"
        assert MemoryType.LONG_TERM.value == "long_term"
        assert MemoryType.META.value == "meta"

    def test_memory_record_creation(self):
        record = MemoryRecord(
            key="test-key", user_id="u1",
            memory_type=MemoryType.LONG_TERM,
            data={"fact": "test"},
        )
        assert record.key == "test-key"
        assert record.version == 1
        assert record.data == {"fact": "test"}

    def test_memory_query_defaults(self):
        query = MemoryQuery()
        assert query.limit == 10
        assert query.offset == 0
