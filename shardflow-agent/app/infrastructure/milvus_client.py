"""Milvus client for memory and strategy vector operations.

Extends the existing pymilvus integration (kb_pipeline.py) with
memory-specific and strategy-specific vector CRUD and search operations.
"""
import logging
import time
from typing import Optional

from pymilvus import (
    connections,
    utility,
    Collection,
)

from app.config import settings

logger = logging.getLogger(__name__)

MEMORY_COLLECTION = "memory_vectors"
STRATEGY_COLLECTION = "strategy_vectors"

SEARCH_PROFILES: dict[str, dict] = {
    "fast": {"metric_type": "COSINE", "params": {"nprobe": 16}},
    "balanced": {"metric_type": "COSINE", "params": {"nprobe": 64}},
    "accurate": {"metric_type": "COSINE", "params": {"nprobe": 128}},
}

_connected: bool = False


def _ensure_connection() -> None:
    """Ensure Milvus connection is established. Idempotent."""
    global _connected
    if _connected:
        return
    connections.connect(
        alias="default",
        host=settings.milvus_host,
        port=settings.milvus_port,
        db_name=settings.milvus_db_name,
    )
    _connected = True
    logger.info("Memory Milvus client connected to %s:%d db=%s",
                settings.milvus_host, settings.milvus_port, settings.milvus_db_name)


def _get_collection(name: str) -> Optional[Collection]:
    """Get a Milvus collection by name, or None if it doesn't exist."""
    _ensure_connection()
    if not utility.has_collection(name):
        logger.warning("Collection %s does not exist", name)
        return None
    return Collection(name)


# ── Memory Vector Operations ──

async def insert_memory_vector(
    chunk_id: str,
    user_id: str,
    memory_type: str,
    category: str,
    content_vector: list[float],
    content_text: str,
    confidence: float = 1.0,
) -> bool:
    """Insert a memory chunk vector into memory_vectors collection."""
    col = _get_collection(MEMORY_COLLECTION)
    if col is None:
        logger.error("Cannot insert: collection %s not found", MEMORY_COLLECTION)
        return False

    try:
        col.insert([
            [chunk_id],
            [user_id],
            [memory_type],
            [category],
            [content_vector],
            [content_text],
            [confidence],
            [int(time.time())],
        ])
        col.flush()
        logger.debug("Inserted memory vector: %s", chunk_id)
        return True
    except Exception as e:
        logger.error("Failed to insert memory vector %s: %s", chunk_id, e)
        return False


async def search_memory_vectors(
    query_vector: list[float],
    user_id: str,
    memory_type: str | None = None,
    category: str | None = None,
    top_k: int = 10,
    similarity_threshold: float = 0.75,
    search_profile: str = "balanced",
) -> list[dict]:
    """Search memory vectors by semantic similarity.

    Args:
        query_vector: Embedding vector of the query.
        user_id: Filter by user.
        memory_type: Optional filter (semantic|episodic).
        category: Optional filter.
        top_k: Number of results.
        similarity_threshold: Minimum COSINE similarity.
        search_profile: Search profile name ("fast", "balanced", "accurate").

    Returns:
        List of dicts with chunk_id, content_text, confidence, distance.
    """
    col = _get_collection(MEMORY_COLLECTION)
    if col is None:
        return []

    # Build filter expression
    expr = f'user_id == "{user_id}"'
    if memory_type:
        expr += f' && memory_type == "{memory_type}"'
    if category:
        expr += f' && category == "{category}"'

    search_params = SEARCH_PROFILES.get(search_profile, SEARCH_PROFILES["balanced"])

    try:
        col.load()
        results = col.search(
            data=[query_vector],
            anns_field="content_vector",
            param=search_params,
            limit=top_k,
            expr=expr,
            output_fields=["chunk_id", "content_text", "confidence", "memory_type", "category"],
        )

        hits = []
        for hit in results[0]:
            if hit.distance >= similarity_threshold:
                hits.append({
                    "chunk_id": hit.entity.get("chunk_id"),
                    "content_text": hit.entity.get("content_text"),
                    "confidence": hit.entity.get("confidence"),
                    "similarity_score": hit.distance,
                    "memory_type": hit.entity.get("memory_type"),
                    "category": hit.entity.get("category"),
                })
        return hits
    except Exception as e:
        logger.error("Memory vector search failed: %s", e)
        return []


async def delete_memory_vector(chunk_id: str) -> bool:
    """Delete a memory vector by chunk_id."""
    col = _get_collection(MEMORY_COLLECTION)
    if col is None:
        return False
    try:
        col.delete(expr=f'chunk_id == "{chunk_id}"')
        logger.debug("Deleted memory vector: %s", chunk_id)
        return True
    except Exception as e:
        logger.error("Failed to delete memory vector %s: %s", chunk_id, e)
        return False


# ── Strategy Vector Operations ──

async def insert_strategy_vector(
    record_id: str,
    user_id: str,
    task_type: str,
    query_vector: list[float],
    query_pattern: str,
    success_score: float = 0.0,
) -> bool:
    """Insert a strategy record vector into strategy_vectors collection."""
    col = _get_collection(STRATEGY_COLLECTION)
    if col is None:
        logger.error("Cannot insert: collection %s not found", STRATEGY_COLLECTION)
        return False

    try:
        col.insert([
            [record_id],
            [user_id],
            [task_type],
            [query_vector],
            [query_pattern],
            [success_score],
            [int(time.time())],
        ])
        col.flush()
        logger.debug("Inserted strategy vector: %s", record_id)
        return True
    except Exception as e:
        logger.error("Failed to insert strategy vector %s: %s", record_id, e)
        return False


async def search_strategy_vectors(
    query_vector: list[float],
    user_id: str,
    task_type: str | None = None,
    top_k: int = 3,
    min_similarity: float = 0.7,
    search_profile: str = "balanced",
) -> list[dict]:
    """Search strategy vectors by semantic similarity.

    Args:
        query_vector: Embedding vector of the query.
        user_id: Filter by user.
        task_type: Optional filter.
        top_k: Number of results.
        min_similarity: Minimum COSINE similarity.
        search_profile: Search profile name ("fast", "balanced", "accurate").

    Returns:
        List of dicts with record_id, query_pattern, success_score, similarity_score.
    """
    col = _get_collection(STRATEGY_COLLECTION)
    if col is None:
        return []

    expr = f'user_id == "{user_id}"'
    if task_type:
        expr += f' && task_type == "{task_type}"'

    search_params = SEARCH_PROFILES.get(search_profile, SEARCH_PROFILES["balanced"])

    try:
        col.load()
        results = col.search(
            data=[query_vector],
            anns_field="query_vector",
            param=search_params,
            limit=top_k,
            expr=expr,
            output_fields=["record_id", "query_pattern", "success_score", "task_type"],
        )

        hits = []
        for hit in results[0]:
            if hit.distance >= min_similarity:
                hits.append({
                    "record_id": hit.entity.get("record_id"),
                    "query_pattern": hit.entity.get("query_pattern"),
                    "success_score": hit.entity.get("success_score"),
                    "similarity_score": hit.distance,
                    "task_type": hit.entity.get("task_type"),
                })
        return hits
    except Exception as e:
        logger.error("Strategy vector search failed: %s", e)
        return []


async def delete_strategy_vector(record_id: str) -> bool:
    """Delete a strategy vector by record_id."""
    col = _get_collection(STRATEGY_COLLECTION)
    if col is None:
        return False
    try:
        col.delete(expr=f'record_id == "{record_id}"')
        logger.debug("Deleted strategy vector: %s", record_id)
        return True
    except Exception as e:
        logger.error("Failed to delete strategy vector %s: %s", record_id, e)
        return False


# ── Batch Insert Operations ──

async def batch_insert_memory_vectors(
    data_list: list[dict],
) -> int:
    """Batch insert multiple memory vectors in a single call.

    Args:
        data_list: List of dicts, each containing:
            chunk_id, user_id, memory_type, category,
            content_vector, content_text, confidence (optional).

    Returns:
        Number of successfully inserted vectors.
    """
    col = _get_collection(MEMORY_COLLECTION)
    if col is None:
        logger.error("Cannot batch insert: collection %s not found", MEMORY_COLLECTION)
        return 0

    try:
        chunk_ids: list[str] = []
        user_ids: list[str] = []
        memory_types: list[str] = []
        categories: list[str] = []
        vectors: list[list[float]] = []
        texts: list[str] = []
        confidences: list[float] = []
        timestamps: list[int] = []

        now = int(time.time())
        for item in data_list:
            chunk_ids.append(item["chunk_id"])
            user_ids.append(item["user_id"])
            memory_types.append(item["memory_type"])
            categories.append(item["category"])
            vectors.append(item["content_vector"])
            texts.append(item["content_text"])
            confidences.append(item.get("confidence", 1.0))
            timestamps.append(now)

        col.insert([
            chunk_ids, user_ids, memory_types, categories,
            vectors, texts, confidences, timestamps,
        ])
        col.flush()
        logger.debug("Batch inserted %d memory vectors", len(data_list))
        return len(data_list)
    except Exception as e:
        logger.error("Failed to batch insert memory vectors: %s", e)
        return 0


async def batch_insert_strategy_vectors(
    data_list: list[dict],
) -> int:
    """Batch insert multiple strategy vectors in a single call.

    Args:
        data_list: List of dicts, each containing:
            record_id, user_id, task_type, query_vector,
            query_pattern, success_score (optional).

    Returns:
        Number of successfully inserted vectors.
    """
    col = _get_collection(STRATEGY_COLLECTION)
    if col is None:
        logger.error("Cannot batch insert: collection %s not found", STRATEGY_COLLECTION)
        return 0

    try:
        record_ids: list[str] = []
        user_ids: list[str] = []
        task_types: list[str] = []
        vectors: list[list[float]] = []
        patterns: list[str] = []
        scores: list[float] = []
        timestamps: list[int] = []

        now = int(time.time())
        for item in data_list:
            record_ids.append(item["record_id"])
            user_ids.append(item["user_id"])
            task_types.append(item["task_type"])
            vectors.append(item["query_vector"])
            patterns.append(item["query_pattern"])
            scores.append(item.get("success_score", 0.0))
            timestamps.append(now)

        col.insert([
            record_ids, user_ids, task_types, vectors,
            patterns, scores, timestamps,
        ])
        col.flush()
        logger.debug("Batch inserted %d strategy vectors", len(data_list))
        return len(data_list)
    except Exception as e:
        logger.error("Failed to batch insert strategy vectors: %s", e)
        return 0


# ── Collection Stats ──

def get_collection_stats(collection_name: str) -> dict | None:
    """Get statistics for a Milvus collection.

    Args:
        collection_name: Name of the collection.

    Returns:
        Dict with row_count and index info, or None if collection not found.
    """
    col = _get_collection(collection_name)
    if col is None:
        return None

    try:
        col.flush()
        row_count = col.num_entities
        indexes = col.indexes
        index_info = []
        for idx in indexes:
            index_info.append({
                "field_name": idx.field_name,
                "index_name": idx.index_name,
                "index_type": idx.params.get("index_type", "unknown"),
                "metric_type": idx.params.get("metric_type", "unknown"),
            })
        return {
            "collection_name": collection_name,
            "row_count": row_count,
            "indexes": index_info,
        }
    except Exception as e:
        logger.error("Failed to get collection stats for %s: %s", collection_name, e)
        return None
