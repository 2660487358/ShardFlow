"""KnowledgeSearchAdapter: hybrid retrieval (vector + BM25) with rerank for personal KB.

Integrates with RetrievalOrchestrator as a dynamically-mountable search source.
Uses LlamaIndex HybridRetriever + SentenceTransformerRerank for high-quality results.

Quantitative targets:
    - P95 latency ≤ 500ms (Milvus HNSW)
    - P99 latency ≤ 800ms
    - Top-5 Recall@5 ≥ 85% (100 chunks scale)
    - Top-3 MRR ≥ 0.80 (after rerank)
"""
import asyncio
import logging
import time
from typing import Optional

from llama_index.core import VectorStoreIndex, StorageContext, Settings as LlamaSettings
from llama_index.core.indices.query.schema import QueryBundle
from llama_index.core.postprocessor import SentenceTransformerRerank
from llama_index.core.retrievers import AutoMergingRetriever, BaseRetriever
from llama_index.retrievers.bm25 import BM25Retriever
from llama_index.core.schema import NodeWithScore

from app.config import settings
from app.layers.retrieval.kb_pipeline import (
    init_llama_index, connect_milvus, get_vector_store, get_collection_stats,
)
from app.models.search_result import SearchResult

logger = logging.getLogger(__name__)

# Cache of loaded indices: {collection_name: VectorStoreIndex}
_index_cache: dict[str, VectorStoreIndex] = {}

# Cache of BM25 retrievers keyed by collection name
_bm25_cache: dict[str, BM25Retriever] = {}


class _PrecomputedRetriever(BaseRetriever):
    """Retriever that returns pre-computed nodes, used to feed RRF results into AutoMerging."""

    def __init__(self, nodes: list[NodeWithScore]):
        super().__init__()
        self._nodes = nodes

    def _retrieve(self, query_bundle: QueryBundle) -> list[NodeWithScore]:
        return self._nodes


def _get_or_load_index(collection_name: str) -> VectorStoreIndex:
    """Get or load a VectorStoreIndex for a collection. Cached in memory."""
    if collection_name in _index_cache:
        return _index_cache[collection_name]

    init_llama_index()
    connect_milvus()
    vector_store = get_vector_store(collection_name)
    storage_context = StorageContext.from_defaults(vector_store=vector_store)

    index = VectorStoreIndex.from_vector_store(
        vector_store=vector_store,
        storage_context=storage_context,
        embed_model=LlamaSettings.embed_model,
    )
    _index_cache[collection_name] = index
    logger.info("Loaded index for collection '%s'", collection_name)
    return index


def invalidate_index_cache(collection_name: str | None = None) -> None:
    """Clear index cache for a specific collection or all."""
    if collection_name:
        _index_cache.pop(collection_name, None)
        _bm25_cache.pop(collection_name, None)
    else:
        _index_cache.clear()
        _bm25_cache.clear()


def _build_bm25_retriever(collection_name: str, kb_id: str | None = None) -> BM25Retriever:
    """Build or retrieve a cached BM25 keyword retriever from the collection's documents.

    Args:
        collection_name: Milvus collection name (e.g. kb_chunks_user123).
        kb_id: Optional knowledge base ID to filter chunks within the collection.
    """
    import pymilvus
    from llama_index.core import Document as LlamaDocument
    cache_key = f"{collection_name}:{kb_id or 'all'}"
    if cache_key in _bm25_cache:
        return _bm25_cache[cache_key]

    connect_milvus()
    try:
        col = pymilvus.Collection(collection_name)
        col.load()
        # Build filter expression: prefer status == ACTIVE if field exists, otherwise fetch all
        expr_parts = []
        try:
            # Check if status field exists in schema
            field_names = [f.name for f in col.schema.fields]
            if "status" in field_names:
                expr_parts.append('status == "ACTIVE"')
        except Exception:
            pass
        if kb_id:
            expr_parts.append(f'collection_id == "{kb_id}"')
        expr = " && ".join(expr_parts) if expr_parts else ""

        results = col.query(
            expr=expr or None,
            output_fields=["chunk_text"],
            limit=5000,
        )
        nodes = []
        for r in results:
            text = r.get("chunk_text", "")
            if text:
                nodes.append(LlamaDocument(text=text))
        if not nodes:
            logger.warning("BM25: no chunks found for '%s' (expr=%s), skipping", collection_name, expr)
            return None
        bm25 = BM25Retriever.from_defaults(nodes=nodes, similarity_top_k=settings.kb_retrieval_top_k * 3)
        _bm25_cache[cache_key] = bm25
        logger.info("Built BM25 retriever for '%s' (kb_id=%s) with %d documents", collection_name, kb_id, len(nodes))
        return bm25
    except Exception as e:
        logger.warning("BM25 build failed for '%s': %s, falling back to vector-only", collection_name, e)
        return None


class KnowledgeSearchAdapter:
    """个人知识库检索适配器 — hybrid retrieval with AutoMerging + Rerank."""

    def __init__(self):
        self.source_name = "knowledge_base"

    async def search(
        self,
        query: str,
        collection_name: str,
        top_k: int | None = None,
        threshold: float | None = None,
        kb_id: str | None = None,
    ) -> list[SearchResult]:
        """Execute hybrid search against the knowledge base.

        Args:
            query: Search query string.
            collection_name: Milvus collection name (e.g. kb_chunks_user123).
            top_k: Number of results to return.
            threshold: Minimum relevance score threshold.
            kb_id: Optional knowledge base ID to filter within the collection.
        """
        start = time.monotonic()

        top_k = top_k or settings.kb_retrieval_top_k
        threshold = threshold or settings.kb_retrieval_similarity_threshold

        try:
            stats = get_collection_stats(collection_name)
            if not stats["exists"] or stats["num_entities"] == 0:
                logger.debug("Collection '%s' empty or missing, skip KB search", collection_name)
                return []

            index = await asyncio.to_thread(_get_or_load_index, collection_name)

            retriever = index.as_retriever(
                similarity_top_k=top_k * 3,
                vector_store_query_mode="default",
            )

            # Hybrid: merge BM25 keyword results with vector results via RRF
            bm25_retriever = await asyncio.to_thread(_build_bm25_retriever, collection_name, kb_id)
            if bm25_retriever is not None:
                bm25_nodes = await asyncio.to_thread(bm25_retriever.retrieve, query)
                vector_nodes = await asyncio.to_thread(retriever.retrieve, query)

                # RRF (Reciprocal Rank Fusion) merge
                all_nodes = _rrf_merge(vector_nodes, bm25_nodes, top_k * 3)
            else:
                all_nodes = await asyncio.to_thread(retriever.retrieve, query)

            # Filter by kb_id if specified (collection_id metadata on nodes)
            if kb_id and all_nodes:
                filtered = []
                for node in all_nodes:
                    node_kb_id = node.metadata.get("collection_id", "") if node.metadata else ""
                    if node_kb_id == kb_id:
                        filtered.append(node)
                if filtered:
                    all_nodes = filtered
                # If no nodes match the kb_id filter, keep all (may be old data without collection_id)

            if not all_nodes:
                return []

            # AutoMerging: feed RRF-merged results via PrecomputedRetriever
            # so that parent-child merging works on the hybrid results, not just vector results
            precomputed = _PrecomputedRetriever(all_nodes)
            auto_merging = AutoMergingRetriever(
                precomputed,
                index.storage_context,
                verbose=False,
            )
            nodes = await asyncio.to_thread(auto_merging.retrieve, query)

            if not nodes:
                return []

            reranker = SentenceTransformerRerank(top_n=top_k)
            nodes = await asyncio.to_thread(
                reranker.postprocess_nodes, nodes, QueryBundle(query_str=query)
            )

            results: list[SearchResult] = []
            for node in nodes:
                score = float(getattr(node, 'score', 0.0) or 0.0)
                if score < threshold:
                    continue
                results.append(SearchResult(
                    source=self.source_name,
                    title=str(node.metadata.get("filename", collection_name)),
                    snippet=node.text[:500] if node.text else "",
                    url=f"internal://kb/{collection_name}/{node.node_id}",
                    relevance_score=score,
                    metadata={
                        "document_id": node.metadata.get("document_id", ""),
                        "collection_name": collection_name,
                        "chunk_index": node.metadata.get("chunk_index", 0),
                        "node_id": node.node_id,
                    },
                ))

            elapsed_ms = (time.monotonic() - start) * 1000
            logger.info("KB search '%s': %d results in %.0fms", query[:50], len(results), elapsed_ms)
            return results

        except Exception as e:
            logger.error("KB search failed for '%s': %s", collection_name, e)
            return []


knowledge_searcher = KnowledgeSearchAdapter()


def _rrf_merge(list_a: list, list_b: list, top_k: int, k: int = 60) -> list:
    """Reciprocal Rank Fusion merge of two ranked lists."""
    scores: dict[str, tuple[float, object]] = {}

    for rank, node in enumerate(list_a):
        node_id = node.node_id if hasattr(node, 'node_id') else str(hash(node.text))
        rrf = 1.0 / (k + rank + 1)
        scores[node_id] = (rrf, node)

    for rank, node in enumerate(list_b):
        node_id = node.node_id if hasattr(node, 'node_id') else str(hash(node.text))
        rrf = 1.0 / (k + rank + 1)
        if node_id in scores:
            prev, _ = scores[node_id]
            scores[node_id] = (prev + rrf, node)
        else:
            scores[node_id] = (rrf, node)

    merged = sorted(scores.values(), key=lambda x: x[0], reverse=True)
    return [node for _, node in merged[:top_k]]
