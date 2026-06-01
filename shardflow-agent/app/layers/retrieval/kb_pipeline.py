"""Knowledge Base Pipeline: LlamaIndex initialization, Milvus connection, document processing.

Handles:
- Singleton Milvus connection management
- LlamaIndex global Settings (embedding model, chunk size)
- Collection lifecycle (create/get/drop)
"""
import logging
import os
from pathlib import Path
from typing import Optional

from llama_index.core import Settings as LlamaSettings
from llama_index.core.node_parser import HierarchicalNodeParser
from llama_index.embeddings.openai import OpenAIEmbedding
from llama_index.vector_stores.milvus import MilvusVectorStore
from pymilvus import connections, utility, Collection

from app.config import settings

logger = logging.getLogger(__name__)

# ── Global init flags ──
_llama_initialized: bool = False
_milvus_connected: bool = False


def init_llama_index() -> None:
    """Initialize LlamaIndex global settings. Idempotent."""
    global _llama_initialized
    if _llama_initialized:
        return

    embed_model = OpenAIEmbedding(
        model=settings.kb_embedding_model,
        dimensions=settings.kb_embedding_dim,
        api_key=settings.llm_api_key,
        api_base=settings.llm_base_url if settings.llm_base_url else None,
    )
    LlamaSettings.embed_model = embed_model
    LlamaSettings.chunk_size = settings.kb_chunk_size
    LlamaSettings.chunk_overlap = settings.kb_chunk_overlap
    _llama_initialized = True
    logger.info("LlamaIndex global settings initialized (embed=%s, dim=%d, chunk=%d)",
                settings.kb_embedding_model, settings.kb_embedding_dim, settings.kb_chunk_size)


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
        )
        _milvus_connected = True
        logger.info("Connected to Milvus at %s:%d", settings.milvus_host, settings.milvus_port)
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
