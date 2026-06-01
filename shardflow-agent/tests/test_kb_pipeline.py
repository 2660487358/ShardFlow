"""Tests for knowledge base document parsing pipeline."""
import os
import tempfile
import pytest
from pathlib import Path

from app.layers.retrieval.kb_pipeline import parse_document, init_llama_index


@pytest.fixture(autouse=True)
def init():
    """Ensure LlamaIndex settings are initialized before tests."""
    init_llama_index()


class TestParseDocument:
    """Document parsing tests for each supported format."""

    def test_parse_markdown(self):
        with tempfile.NamedTemporaryFile(suffix=".md", mode="w", delete=False, encoding="utf-8") as f:
            f.write("# Title\n\n## Section 1\nThis is paragraph one.\n\n## Section 2\nThis is paragraph two.\n")
            tmp_path = f.name
        try:
            docs = parse_document(tmp_path, "md")
            assert len(docs) >= 1
            assert "Title" in docs[0].text
            assert docs[0].metadata.get("parse_strategy") == "heading"
        finally:
            os.unlink(tmp_path)

    def test_parse_text(self):
        with tempfile.NamedTemporaryFile(suffix=".txt", mode="w", delete=False, encoding="utf-8") as f:
            f.write("First paragraph.\n\nSecond paragraph.\n\nThird paragraph.")
            tmp_path = f.name
        try:
            docs = parse_document(tmp_path, "txt")
            assert len(docs) >= 1
            assert "First paragraph" in docs[0].text
            assert docs[0].metadata.get("parse_strategy") == "paragraph"
        finally:
            os.unlink(tmp_path)

    def test_parse_python(self):
        with tempfile.NamedTemporaryFile(suffix=".py", mode="w", delete=False, encoding="utf-8") as f:
            f.write("def hello():\n    return 'world'\n\nclass Foo:\n    pass\n")
            tmp_path = f.name
        try:
            docs = parse_document(tmp_path, "py")
            assert len(docs) >= 1
            assert "def hello" in docs[0].text
            assert docs[0].metadata.get("parse_strategy") == "ast"
        finally:
            os.unlink(tmp_path)

    def test_parse_unsupported_extension_raises(self):
        with tempfile.NamedTemporaryFile(suffix=".xyz", mode="w", delete=False, encoding="utf-8") as f:
            f.write("some content")
            tmp_path = f.name
        try:
            with pytest.raises(ValueError, match="Unsupported file type"):
                parse_document(tmp_path, "xyz")
        finally:
            os.unlink(tmp_path)

    def test_parse_empty_file_raises(self):
        with tempfile.NamedTemporaryFile(suffix=".txt", mode="w", delete=False, encoding="utf-8") as f:
            f.write("   \n  ")
            tmp_path = f.name
        try:
            with pytest.raises(RuntimeError, match="empty"):
                parse_document(tmp_path, "txt")
        finally:
            os.unlink(tmp_path)


import asyncio
import uuid


class TestProcessDocument:
    """End-to-end processing pipeline tests (requires Milvus)."""

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_process_markdown_e2e(self):
        from app.layers.retrieval.kb_pipeline import connect_milvus
        if not connect_milvus():
            pytest.skip("Milvus not available")

        collection_name = f"test_kb_{uuid.uuid4().hex[:8]}"

        with tempfile.NamedTemporaryFile(suffix=".md", mode="w", delete=False, encoding="utf-8") as f:
            f.write("# Test Doc\n\n## Section A\nThis is content for section A.\n\n## Section B\nThis is content for section B.\n")
            tmp_path = f.name

        try:
            from app.layers.retrieval.kb_pipeline import process_document
            result = await process_document(
                file_path=tmp_path,
                file_type="md",
                collection_name=collection_name,
                document_id="test-doc-1",
                user_id="test-user",
            )
            assert result["success"] is True, f"Processing failed: {result.get('error')}"
            assert result["chunk_count"] > 0
            assert result["elapsed_ms"] > 0
            assert result["elapsed_ms"] < 10_000, f"Too slow: {result['elapsed_ms']}ms"
        finally:
            from app.layers.retrieval.kb_pipeline import drop_collection
            os.unlink(tmp_path)
            drop_collection(collection_name)
