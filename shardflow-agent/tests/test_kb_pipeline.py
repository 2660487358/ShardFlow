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
