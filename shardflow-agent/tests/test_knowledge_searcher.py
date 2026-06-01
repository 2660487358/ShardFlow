"""Tests for KnowledgeSearchAdapter."""
import pytest
from unittest.mock import AsyncMock, patch, MagicMock


class TestKnowledgeSearchAdapter:
    """Unit tests for KnowledgeSearchAdapter (no Milvus needed)."""

    @pytest.mark.asyncio
    async def test_search_empty_collection_returns_empty(self):
        from app.layers.retrieval.knowledge_searcher import KnowledgeSearchAdapter
        adapter = KnowledgeSearchAdapter()
        with patch("app.layers.retrieval.knowledge_searcher.get_collection_stats") as mock_stats:
            mock_stats.return_value = {"exists": False, "num_entities": 0}
            results = await adapter.search("test query", "nonexistent_collection")
            assert results == []

    @pytest.mark.asyncio
    async def test_search_error_returns_empty(self):
        from app.layers.retrieval.knowledge_searcher import KnowledgeSearchAdapter
        adapter = KnowledgeSearchAdapter()
        with patch("app.layers.retrieval.knowledge_searcher.get_collection_stats") as mock_stats:
            mock_stats.side_effect = RuntimeError("Connection refused")
            results = await adapter.search("test", "bad_collection")
            assert results == []
