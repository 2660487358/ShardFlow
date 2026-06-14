"""Milvus Collection initialization for memory architecture.

Per spec section 6.5.5: Creates memory_vectors and strategy_vectors collections
with IVF_FLAT index and COSINE similarity metric.

Usage:
    python -m scripts.init_milvus_collections
"""
import logging
import sys

from pymilvus import (
    connections,
    utility,
    Collection,
    CollectionSchema,
    FieldSchema,
    DataType,
)

logger = logging.getLogger(__name__)

# Default config — override via env vars or direct call
DEFAULT_HOST = "localhost"
DEFAULT_PORT = 19530
DEFAULT_DB = "shardflow_kb"
EMBEDDING_DIM = 1536  # Per spec: text-embedding-3-small with 1536 dims


def init_memory_vectors_collection(
    host: str = DEFAULT_HOST,
    port: int = DEFAULT_PORT,
    db_name: str = DEFAULT_DB,
    dim: int = EMBEDDING_DIM,
    drop_existing: bool = False,
) -> bool:
    """Create the memory_vectors collection per spec 6.5.5.

    Schema:
        chunk_id      VARCHAR(64)   PRIMARY KEY
        user_id       VARCHAR(64)
        memory_type   VARCHAR(32)   semantic|episodic
        category      VARCHAR(64)
        content_vector FLOAT_VECTOR(dim)
        content_text  VARCHAR(65535)
        confidence    FLOAT
        created_at    TIMESTAMP

    Index: IVF_FLAT with COSINE metric, nlist=4096
    """
    collection_name = "memory_vectors"

    connections.connect(alias="default", host=host, port=port, db_name=db_name)

    if utility.has_collection(collection_name):
        if drop_existing:
            utility.drop_collection(collection_name)
            logger.info("Dropped existing collection: %s", collection_name)
        else:
            logger.info("Collection %s already exists, skipping.", collection_name)
            return True

    fields = [
        FieldSchema(name="chunk_id", dtype=DataType.VARCHAR, max_length=64, is_primary=True),
        FieldSchema(name="user_id", dtype=DataType.VARCHAR, max_length=64),
        FieldSchema(name="memory_type", dtype=DataType.VARCHAR, max_length=32),
        FieldSchema(name="category", dtype=DataType.VARCHAR, max_length=64),
        FieldSchema(name="content_vector", dtype=DataType.FLOAT_VECTOR, dim=dim),
        FieldSchema(name="content_text", dtype=DataType.VARCHAR, max_length=65535),
        FieldSchema(name="confidence", dtype=DataType.FLOAT),
        FieldSchema(name="created_at", dtype=DataType.INT64),  # Unix timestamp
    ]

    schema = CollectionSchema(
        fields=fields,
        description="Memory chunk vector index for semantic search",
    )

    collection = Collection(name=collection_name, schema=schema)

    # Create IVF_FLAT index with COSINE metric
    index_params = {
        "index_type": "IVF_FLAT",
        "metric_type": "COSINE",
        "params": {"nlist": 4096},
    }
    collection.create_index(field_name="content_vector", index_params=index_params)
    collection.load()

    logger.info("Created collection %s with IVF_FLAT index (dim=%d, COSINE)", collection_name, dim)
    return True


def init_strategy_vectors_collection(
    host: str = DEFAULT_HOST,
    port: int = DEFAULT_PORT,
    db_name: str = DEFAULT_DB,
    dim: int = EMBEDDING_DIM,
    drop_existing: bool = False,
) -> bool:
    """Create the strategy_vectors collection per spec 6.5.5.

    Schema:
        record_id      VARCHAR(64)   PRIMARY KEY
        user_id        VARCHAR(64)
        task_type      VARCHAR(64)
        query_vector   FLOAT_VECTOR(dim)
        query_pattern  VARCHAR(512)
        success_score  FLOAT
        created_at     TIMESTAMP

    Index: IVF_FLAT with COSINE metric, nlist=4096
    """
    collection_name = "strategy_vectors"

    connections.connect(alias="default", host=host, port=port, db_name=db_name)

    if utility.has_collection(collection_name):
        if drop_existing:
            utility.drop_collection(collection_name)
            logger.info("Dropped existing collection: %s", collection_name)
        else:
            logger.info("Collection %s already exists, skipping.", collection_name)
            return True

    fields = [
        FieldSchema(name="record_id", dtype=DataType.VARCHAR, max_length=64, is_primary=True),
        FieldSchema(name="user_id", dtype=DataType.VARCHAR, max_length=64),
        FieldSchema(name="task_type", dtype=DataType.VARCHAR, max_length=64),
        FieldSchema(name="query_vector", dtype=DataType.FLOAT_VECTOR, dim=dim),
        FieldSchema(name="query_pattern", dtype=DataType.VARCHAR, max_length=512),
        FieldSchema(name="success_score", dtype=DataType.FLOAT),
        FieldSchema(name="created_at", dtype=DataType.INT64),  # Unix timestamp
    ]

    schema = CollectionSchema(
        fields=fields,
        description="Strategy record vector index for semantic strategy reuse",
    )

    collection = Collection(name=collection_name, schema=schema)

    # Create IVF_FLAT index with COSINE metric
    index_params = {
        "index_type": "IVF_FLAT",
        "metric_type": "COSINE",
        "params": {"nlist": 4096},
    }
    collection.create_index(field_name="query_vector", index_params=index_params)
    collection.load()

    logger.info("Created collection %s with IVF_FLAT index (dim=%d, COSINE)", collection_name, dim)
    return True


def init_all_collections(**kwargs) -> bool:
    """Initialize both memory_vectors and strategy_vectors collections."""
    success = True
    try:
        init_memory_vectors_collection(**kwargs)
    except Exception as e:
        logger.error("Failed to init memory_vectors: %s", e)
        success = False
    try:
        init_strategy_vectors_collection(**kwargs)
    except Exception as e:
        logger.error("Failed to init strategy_vectors: %s", e)
        success = False
    return success


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    ok = init_all_collections()
    sys.exit(0 if ok else 1)
