"""Knowledge Base Pipeline: LlamaIndex initialization, Milvus connection, document processing.

Handles:
- Singleton Milvus connection management
- LlamaIndex global Settings (embedding model, chunk size)
- Collection lifecycle (create/get/drop)
- Dynamic embedding model configuration via config service
"""
import logging
import os
import time
from pathlib import Path
from typing import Optional

from llama_index.core import Document, Settings as LlamaSettings
from llama_index.core.node_parser import HierarchicalNodeParser
from llama_index.embeddings.openai import OpenAIEmbedding
from llama_index.readers.file import PDFReader, DocxReader, MarkdownReader
from llama_index.vector_stores.milvus import MilvusVectorStore
from pymilvus import connections, utility, Collection

from app.config import settings

logger = logging.getLogger(__name__)

# ── Global init flags ──
_llama_initialized: bool = False
_milvus_connected: bool = False


async def _fetch_embedding_config() -> dict:
    """Fetch embedding model config from Java ConfigService for the given model_id."""
    try:
        from app.infrastructure.callback_client import callback_client
        java_client = await callback_client._get_client()
        resp = await java_client.get(
            f"/api/v1/models/{settings.kb_embedding_model}/config",
            headers={"X-API-Key": settings.java_api_key or settings.llm_api_key},
        )
        resp.raise_for_status()
        data = resp.json()
        if isinstance(data, dict) and "data" in data:
            return data["data"]
        return data
    except Exception as e:
        logger.warning("Failed to fetch embedding config, using global settings: %s", e)
        return {
            "base_url": settings.llm_base_url,
            "api_key": settings.llm_api_key,
            "model": settings.kb_embedding_model,
        }


def init_llama_index(embedding_config: dict | None = None) -> None:
    """Initialize LlamaIndex global settings. Idempotent.

    Args:
        embedding_config: Optional pre-fetched config with api_key, base_url, model.
    """
    global _llama_initialized
    if _llama_initialized:
        return

    if embedding_config is None:
        # Synchronous fallback: use global settings
        embedding_config = {
            "api_key": settings.llm_api_key,
            "base_url": settings.llm_base_url if settings.llm_base_url else None,
            "model": settings.kb_embedding_model,
        }

    embed_model = OpenAIEmbedding(
        model=embedding_config.get("model", settings.kb_embedding_model),
        dimensions=settings.kb_embedding_dim,
        api_key=embedding_config.get("api_key", settings.llm_api_key),
        api_base=embedding_config.get("base_url") if embedding_config.get("base_url") else None,
    )
    LlamaSettings.embed_model = embed_model
    LlamaSettings.chunk_size = settings.kb_chunk_size
    LlamaSettings.chunk_overlap = settings.kb_chunk_overlap
    _llama_initialized = True
    logger.info("LlamaIndex global settings initialized (embed=%s, dim=%d, chunk=%d)",
                settings.kb_embedding_model, settings.kb_embedding_dim, settings.kb_chunk_size)


async def init_llama_index_async() -> None:
    """Async version that fetches embedding config from config service."""
    global _llama_initialized
    if _llama_initialized:
        return
    config = await _fetch_embedding_config()
    init_llama_index(config)


def connect_milvus() -> bool:
    """Connect to Milvus. Idempotent, returns True on success."""
    global _milvus_connected
    if _milvus_connected:
        return True
    try:
        connections.connect(
            alias="default",
            host=settings.milvus_host,
            port=settings.milvus_port,
            db_name=settings.milvus_db_name,
        )
        _milvus_connected = True
        logger.info("Connected to Milvus at %s:%d db=%s",
                     settings.milvus_host, settings.milvus_port, settings.milvus_db_name)
        return True
    except Exception as e:
        logger.error("Failed to connect to Milvus: %s", e)
        _milvus_connected = False
        return False


def get_vector_store(collection_name: str, overwrite: bool = False) -> MilvusVectorStore:
    """Get or create a MilvusVectorStore for a collection."""
    connect_milvus()
    init_llama_index()

    return MilvusVectorStore(
        collection_name=collection_name,
        dim=settings.kb_embedding_dim,
        uri=f"http://{settings.milvus_host}:{settings.milvus_port}",
        overwrite=overwrite,
        similarity_metric="COSINE",
        index_config={
            "index_type": "HNSW",
            "params": {"M": 16, "efConstruction": 200},
        },
    )


def drop_collection(collection_name: str) -> bool:
    """Drop a Milvus collection. Returns True if dropped or didn't exist."""
    connect_milvus()
    try:
        if utility.has_collection(collection_name):
            utility.drop_collection(collection_name)
            logger.info("Dropped Milvus collection: %s", collection_name)
        return True
    except Exception as e:
        logger.error("Failed to drop collection %s: %s", collection_name, e)
        return False


def get_collection_stats(collection_name: str) -> dict:
    """Get collection statistics."""
    connect_milvus()
    try:
        if not utility.has_collection(collection_name):
            return {"exists": False, "num_entities": 0}
        col = Collection(collection_name)
        col.load()
        return {
            "exists": True,
            "num_entities": col.num_entities,
        }
    except Exception as e:
        logger.error("Failed to get stats for %s: %s", collection_name, e)
        return {"exists": False, "num_entities": 0, "error": str(e)}


def create_node_parser() -> HierarchicalNodeParser:
    """Create HierarchicalNodeParser for parent-child indexing.

    Returns a parser that produces:
    - Parent nodes (document level, chunk_size * 3)
    - Child nodes (paragraph level, chunk_size)
    """
    init_llama_index()
    return HierarchicalNodeParser.from_defaults(
        chunk_sizes=[
            settings.kb_chunk_size,           # child: 512 tokens
            settings.kb_chunk_size * 3,       # parent: 1536 tokens
        ],
        chunk_overlap=settings.kb_chunk_overlap,
    )


# ── Document Readers ──

def parse_document(file_path: str, file_type: str) -> list[Document]:
    """Parse a document into LlamaIndex Documents using format-aware readers.

    Args:
        file_path: Absolute path to the uploaded file.
        file_type: Lowercase extension without dot (pdf, docx, md, txt, py, java, ...)

    Returns:
        List of Document objects (usually 1 per file, chunking happens later).

    Raises:
        ValueError: If file_type is unsupported.
        RuntimeError: If parsing fails.
    """
    ext = file_type.lower()

    # ── PDF ──
    if ext == "pdf":
        try:
            reader = PDFReader()
            docs = reader.load_data(file=Path(file_path))
            if not docs:
                raise RuntimeError("PDFReader returned empty")
            return docs
        except Exception as e:
            raise RuntimeError(f"PDF parse failed: {e}") from e

    # ── DOCX ──
    if ext == "docx":
        try:
            reader = DocxReader()
            docs = reader.load_data(file=Path(file_path))
            if not docs:
                raise RuntimeError("DocxReader returned empty")
            return docs
        except Exception as e:
            raise RuntimeError(f"DOCX parse failed: {e}") from e

    # ── Markdown ──
    if ext == "md":
        try:
            reader = MarkdownReader()
            docs = reader.load_data(file=Path(file_path))
            if not docs:
                raise RuntimeError("MarkdownReader returned empty")
            for doc in docs:
                if doc.metadata is None:
                    doc.metadata = {}
                doc.metadata["parse_strategy"] = "heading"
            return docs
        except Exception as e:
            raise RuntimeError(f"MD parse failed: {e}") from e

    # ── Code files ──
    CODE_EXTS = {"py", "java", "ts", "tsx", "js", "go", "rs"}
    if ext in CODE_EXTS:
        return _parse_code_file(file_path, ext)

    # ── Plain text ──
    TXT_EXTS = {"txt", "yaml", "yml", "json", "xml", "csv", "log"}
    if ext in TXT_EXTS:
        return _parse_text_file(file_path, ext)

    raise ValueError(f"Unsupported file type: .{ext}")


def _parse_code_file(file_path: str, ext: str) -> list[Document]:
    """Parse code files — split by lines, preserve raw content for chunking."""
    text = Path(file_path).read_text(encoding="utf-8", errors="replace")
    if not text.strip():
        raise RuntimeError(f"Code file is empty: {file_path}")
    return [Document(
        text=text,
        metadata={
            "parse_strategy": "ast",
            "language": ext,
            "filename": os.path.basename(file_path),
        },
    )]


def _parse_text_file(file_path: str, ext: str) -> list[Document]:
    """Parse plain text files — paragraph splitting by double newline."""
    text = Path(file_path).read_text(encoding="utf-8", errors="replace")
    if not text.strip():
        raise RuntimeError(f"Text file is empty: {file_path}")
    return [Document(
        text=text,
        metadata={
            "parse_strategy": "paragraph",
            "file_type": ext,
            "filename": os.path.basename(file_path),
        },
    )]


# ── Processing Pipeline ──

from typing import Callable

from llama_index.core.ingestion import IngestionPipeline

ProgressCallback = Callable[[str, dict], None]  # (status, metadata) -> None


async def process_document(
    file_path: str,
    file_type: str,
    collection_name: str,
    document_id: str,
    user_id: str,
    kb_id: str = "",
    progress_callback: ProgressCallback | None = None,
) -> dict:
    """Full document processing pipeline: parse → chunk → embed → store.

    Args:
        file_path: Absolute path to uploaded document.
        file_type: Lowercase extension (pdf, docx, md, txt, py, ...).
        collection_name: Milvus collection name (e.g. kb_chunks_user123).
        document_id: PostgreSQL kb_document.id for tracking.
        user_id: User ID for metadata tagging.
        kb_id: Knowledge base collection ID (PostgreSQL kb_collection.id) for filtering.
        progress_callback: Optional callback(status, metadata) for status updates.

    Returns:
        dict with keys: success, chunk_count, elapsed_ms, error (if failed).
    """
    start_time = time.monotonic()
    result = {
        "success": False,
        "document_id": document_id,
        "chunk_count": 0,
        "elapsed_ms": 0,
        "error": None,
    }

    def _notify(status: str, extra: dict | None = None):
        if progress_callback:
            meta = {"document_id": document_id, "status": status, **(extra or {})}
            progress_callback(status, meta)

    try:
        # Step 1: Parse document
        _notify("PARSING")
        await init_llama_index_async()
        docs = parse_document(file_path, file_type)
        if not docs:
            raise RuntimeError("Document parsing produced zero documents")

        # Step 2: Create node parser
        _notify("CHUNKING")
        node_parser = create_node_parser()

        # Step 3: Create vector store
        _notify("EMBEDDING")
        vector_store = get_vector_store(collection_name)

        # Step 4: Set up ingestion pipeline
        pipeline = IngestionPipeline(
            transformations=[
                node_parser,
                LlamaSettings.embed_model,
            ],
            vector_store=vector_store,
        )

        # Step 5: Run pipeline
        import asyncio
        nodes = await asyncio.to_thread(pipeline.run, documents=docs)

        # Step 6: Tag nodes with metadata (DR-3 compatible)
        chunk_count = 0
        now_ts = int(time.time())
        for i, node in enumerate(nodes):
            if node.metadata is None:
                node.metadata = {}
            node.metadata["document_id"] = document_id
            node.metadata["collection_id"] = kb_id or collection_name  # Use actual kb_id for filtering
            node.metadata["user_id"] = user_id
            node.metadata["tenant_id"] = user_id  # Same as user_id for single-tenant mode
            node.metadata["chunk_index"] = i
            node.metadata["filename"] = os.path.basename(file_path)
            node.metadata["status"] = "ACTIVE"
            node.metadata["create_time"] = now_ts
            chunk_count += 1

        elapsed = (time.monotonic() - start_time) * 1000
        result["success"] = True
        result["chunk_count"] = chunk_count
        result["elapsed_ms"] = elapsed

        _notify("READY", {"chunk_count": chunk_count, "elapsed_ms": elapsed})
        logger.info("Document %s processed: %d chunks in %.0fms", document_id, chunk_count, elapsed)
        return result

    except Exception as e:
        elapsed = (time.monotonic() - start_time) * 1000
        result["error"] = str(e)
        result["elapsed_ms"] = elapsed
        _notify("ERROR", {"error": str(e)})
        logger.error("Document %s processing failed: %s (%.0fms)", document_id, e, elapsed)
        return result
