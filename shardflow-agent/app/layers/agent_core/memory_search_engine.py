"""MemorySearchEngine — 记忆检索引擎 (FR-RR-001 ~ FR-RR-004).

Implements the complete memory retrieval pipeline:
- FR-RR-001: Vector semantic search (Milvus ANN, Top-K=10, COSINE>=0.75)
- FR-RR-002: Structured query (time/type/tag/confidence filtering)
- FR-RR-003: Hybrid search (structured filter → vector ranking → fusion score)
- FR-RR-004: Reranking (coarse Top-50 → Cross-Encoder → business rules → Top-5)

Per spec section 4.4:
- Vector search: Milvus ANN with COSINE >= 0.75, Top-K default 10, max 50
- Structured query: time, type, tag, confidence, category filtering
- Hybrid: alpha * vector_sim + beta * structured_match + gamma * time_decay
- Reranking: 3-stage pipeline for high-quality results
"""
import logging
import math
import time
from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, Field

from app.infrastructure.milvus_client import search_memory_vectors
from app.layers.agent_core.memory_orchestrator import memory_orchestrator
from app.models.memory import MemoryQuery, MemoryQueryResult, MemoryType

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Search request / response models
# ---------------------------------------------------------------------------

class SearchFilters(BaseModel):
    """Filters for structured and hybrid search."""
    memory_types: list[MemoryType] = Field(default_factory=list)
    categories: list[str] = Field(default_factory=list)
    created_after: datetime | None = None
    created_before: datetime | None = None
    min_confidence: float = 0.0
    max_confidence: float = 1.0
    tags: list[str] = Field(default_factory=list)

    model_config = {"extra": "allow"}


class SearchRequest(BaseModel):
    """Unified search request for all search modes."""
    user_id: str
    query: str = ""
    query_vector: list[float] = Field(default_factory=list)
    search_type: str = "hybrid"  # vector | structured | hybrid
    top_k: int = 10
    similarity_threshold: float = 0.75
    filters: SearchFilters = Field(default_factory=SearchFilters)

    model_config = {"extra": "allow"}


class SearchResult(BaseModel):
    """A single search result with scoring details."""
    memory_id: str = ""
    content_text: str = ""
    similarity_score: float = 0.0
    confidence: float = 0.0
    category: str = ""
    memory_type: MemoryType = MemoryType.SEMANTIC
    metadata: dict[str, Any] = Field(default_factory=dict)
    # Scoring breakdown for hybrid search
    vector_score: float = 0.0
    structured_score: float = 0.0
    time_decay_score: float = 0.0
    fusion_score: float = 0.0

    model_config = {"extra": "allow"}


class SearchResponse(BaseModel):
    """Response from a memory search operation."""
    results: list[SearchResult] = Field(default_factory=list)
    total: int = 0
    search_type: str = ""
    search_time_ms: int = 0

    model_config = {"extra": "allow"}


# ---------------------------------------------------------------------------
# Fusion score weights (FR-RR-003)
# ---------------------------------------------------------------------------

class FusionWeights:
    """Weights for hybrid search fusion score.

    fusion = alpha * vector_sim + beta * structured_match + gamma * time_decay
    """
    ALPHA = 0.5   # Vector similarity weight
    BETA = 0.3    # Structured match weight
    GAMMA = 0.2   # Time decay weight

    # Time decay half-life in days (memories older than this get lower scores)
    TIME_DECAY_HALF_LIFE_DAYS = 30.0


# ---------------------------------------------------------------------------
# MemorySearchEngine
# ---------------------------------------------------------------------------

class MemorySearchEngine:
    """Unified memory search engine supporting vector, structured, and hybrid
    search with optional reranking.

    Usage:
        engine = MemorySearchEngine()
        response = await engine.search(SearchRequest(
            user_id="user_001",
            query="用户常用的信息源偏好",
            search_type="hybrid",
        ))
    """

    # FR-RR-001: Default search parameters
    DEFAULT_TOP_K: int = 10
    MAX_TOP_K: int = 50
    DEFAULT_SIMILARITY_THRESHOLD: float = 0.75

    # FR-RR-004: Reranking parameters
    RERANK_COARSE_TOP_K: int = 50
    RERANK_FINAL_TOP_K: int = 5

    def __init__(self) -> None:
        # L0 cache for recent search results (query_hash -> SearchResponse)
        self._search_cache: dict[str, SearchResponse] = {}
        self._cache_max_size: int = 100

    # ------------------------------------------------------------------
    # FR-RR-001: Vector semantic search
    # ------------------------------------------------------------------

    async def vector_search(
        self,
        user_id: str,
        query_vector: list[float],
        memory_type: str | None = None,
        category: str | None = None,
        top_k: int = 10,
        similarity_threshold: float = 0.75,
    ) -> list[SearchResult]:
        """Execute vector semantic search against Milvus.

        Per FR-RR-001:
        - Top-K: default 10, max 50
        - Similarity threshold: COSINE >= 0.75
        - Filter: user_id + memory_type + category
        """
        top_k = min(top_k, self.MAX_TOP_K)
        start_time = time.monotonic()

        hits = await search_memory_vectors(
            query_vector=query_vector,
            user_id=user_id,
            memory_type=memory_type,
            category=category,
            top_k=top_k,
            similarity_threshold=similarity_threshold,
        )

        elapsed_ms = int((time.monotonic() - start_time) * 1000)

        results: list[SearchResult] = []
        for hit in hits:
            result = SearchResult(
                memory_id=hit.get("chunk_id", ""),
                content_text=hit.get("content_text", ""),
                similarity_score=hit.get("similarity_score", 0.0),
                confidence=hit.get("confidence", 0.0),
                category=hit.get("category", ""),
                memory_type=MemoryType(hit.get("memory_type", "semantic")),
                vector_score=hit.get("similarity_score", 0.0),
                fusion_score=hit.get("similarity_score", 0.0),
            )
            results.append(result)

        logger.info(
            "Vector search for user %s: %d results in %dms (top_k=%d, threshold=%.2f)",
            user_id, len(results), elapsed_ms, top_k, similarity_threshold,
        )

        return results

    # ------------------------------------------------------------------
    # FR-RR-002: Structured query
    # ------------------------------------------------------------------

    async def structured_search(
        self,
        user_id: str,
        filters: SearchFilters,
        limit: int = 10,
        offset: int = 0,
    ) -> list[SearchResult]:
        """Execute structured query against memory store.

        Per FR-RR-002:
        - Filter by time, type, tag, confidence
        - Support combined conditions
        """
        start_time = time.monotonic()
        results: list[SearchResult] = []

        # Search each requested memory type
        memory_types = filters.memory_types if filters.memory_types else [
            MemoryType.SEMANTIC, MemoryType.EPISODIC,
        ]

        for mt in memory_types:
            mq = MemoryQuery(
                memory_type=mt,
                tags=filters.tags,
                created_after=filters.created_after,
                created_before=filters.created_before,
                limit=limit * 2,  # Over-fetch for post-filtering
                offset=offset,
            )

            records = await memory_orchestrator.search(user_id, mt, mq)

            for record in records:
                data = record.data
                confidence = data.get("confidence", 0.0)
                category = data.get("category", "")

                # Apply confidence filter
                if confidence < filters.min_confidence or confidence > filters.max_confidence:
                    continue

                # Apply category filter
                if filters.categories and category not in filters.categories:
                    continue

                # Compute structured match score
                structured_score = self._compute_structured_score(
                    data, filters,
                )

                result = SearchResult(
                    memory_id=data.get("memory_id", record.key),
                    content_text=data.get("text", ""),
                    confidence=confidence,
                    category=category,
                    memory_type=mt,
                    metadata=data,
                    structured_score=structured_score,
                    fusion_score=structured_score,
                )
                results.append(result)

        # Sort by structured score descending
        results.sort(key=lambda r: r.structured_score, reverse=True)

        # Apply limit
        results = results[:limit]

        elapsed_ms = int((time.monotonic() - start_time) * 1000)
        logger.info(
            "Structured search for user %s: %d results in %dms",
            user_id, len(results), elapsed_ms,
        )

        return results

    # ------------------------------------------------------------------
    # FR-RR-003: Hybrid search (recommended default)
    # ------------------------------------------------------------------

    async def hybrid_search(
        self,
        user_id: str,
        query: str,
        query_vector: list[float],
        filters: SearchFilters,
        top_k: int = 10,
        similarity_threshold: float = 0.75,
    ) -> list[SearchResult]:
        """Execute hybrid search: structured filter → vector ranking → fusion score.

        Per FR-RR-003:
        1. Execute structured filter to narrow candidate set
        2. Execute vector similarity search on candidates
        3. Compute fusion score = alpha * vector_sim + beta * structured_match + gamma * time_decay
        """
        start_time = time.monotonic()

        # Step 1: Structured filter to get candidate set
        candidates = await self.structured_search(
            user_id=user_id,
            filters=filters,
            limit=top_k * 5,  # Over-fetch for vector ranking
        )

        # Step 2: Vector search to get similarity scores
        vector_results = await self.vector_search(
            user_id=user_id,
            query_vector=query_vector,
            top_k=top_k * 3,
            similarity_threshold=similarity_threshold,
        )

        # Build vector score lookup: memory_id -> similarity_score
        vector_scores: dict[str, float] = {}
        for vr in vector_results:
            vector_scores[vr.memory_id] = vr.similarity_score

        # Also check content text matching for vector results not in structured results
        vector_by_text: dict[str, SearchResult] = {}
        for vr in vector_results:
            vector_by_text[vr.content_text[:100]] = vr

        # Step 3: Merge and compute fusion scores
        merged: dict[str, SearchResult] = {}

        # Add structured candidates
        for candidate in candidates:
            sr = SearchResult(
                memory_id=candidate.memory_id,
                content_text=candidate.content_text,
                similarity_score=vector_scores.get(candidate.memory_id, 0.0),
                confidence=candidate.confidence,
                category=candidate.category,
                memory_type=candidate.memory_type,
                metadata=candidate.metadata,
                vector_score=vector_scores.get(candidate.memory_id, 0.0),
                structured_score=candidate.structured_score,
                time_decay_score=self._compute_time_decay(candidate.metadata),
            )
            sr.fusion_score = self._compute_fusion_score(sr)
            merged[sr.memory_id] = sr

        # Add vector results not in structured candidates
        for vr in vector_results:
            if vr.memory_id not in merged:
                sr = SearchResult(
                    memory_id=vr.memory_id,
                    content_text=vr.content_text,
                    similarity_score=vr.similarity_score,
                    confidence=vr.confidence,
                    category=vr.category,
                    memory_type=vr.memory_type,
                    metadata=vr.metadata,
                    vector_score=vr.vector_score,
                    structured_score=0.0,
                    time_decay_score=self._compute_time_decay(vr.metadata),
                )
                sr.fusion_score = self._compute_fusion_score(sr)
                merged[sr.memory_id] = sr

        # Sort by fusion score descending
        results = sorted(merged.values(), key=lambda r: r.fusion_score, reverse=True)
        results = results[:top_k]

        elapsed_ms = int((time.monotonic() - start_time) * 1000)
        logger.info(
            "Hybrid search for user %s: %d results in %dms (fusion: alpha=%.1f, beta=%.1f, gamma=%.1f)",
            user_id, len(results), elapsed_ms,
            FusionWeights.ALPHA, FusionWeights.BETA, FusionWeights.GAMMA,
        )

        return results

    # ------------------------------------------------------------------
    # FR-RR-004: Reranking
    # ------------------------------------------------------------------

    async def rerank(
        self,
        results: list[SearchResult],
        query: str,
        top_k: int = 5,
    ) -> list[SearchResult]:
        """Three-stage reranking pipeline.

        Per FR-RR-004:
        1. Coarse ranking: vector results Top-50
        2. Fine ranking: Cross-Encoder reranking model
        3. Business rule filtering: exclude deleted/expired/low-confidence

        Output: Top-5 most relevant memory chunks.
        """
        if not results:
            return []

        # Stage 1: Coarse ranking — take top candidates
        coarse_top = min(len(results), self.RERANK_COARSE_TOP_K)
        candidates = sorted(results, key=lambda r: r.fusion_score, reverse=True)[:coarse_top]

        # Stage 2: Fine ranking — Cross-Encoder reranking
        reranked = await self._cross_encoder_rerank(candidates, query)

        # Stage 3: Business rule filtering
        filtered = self._apply_business_rules(reranked)

        # Return top-k
        return filtered[:top_k]

    async def _cross_encoder_rerank(
        self,
        candidates: list[SearchResult],
        query: str,
    ) -> list[SearchResult]:
        """Cross-Encoder reranking for fine-grained relevance scoring.

        Uses LLM-based reranking when available, falls back to
        heuristic scoring.
        """
        if not candidates:
            return candidates

        # Try LLM-based reranking
        try:
            reranked = await self._llm_rerank(candidates, query)
            if reranked:
                return reranked
        except Exception as e:
            logger.debug("LLM reranking failed, using heuristic fallback: %s", e)

        # Fallback: heuristic reranking based on content overlap
        return self._heuristic_rerank(candidates, query)

    async def _llm_rerank(
        self,
        candidates: list[SearchResult],
        query: str,
    ) -> list[SearchResult] | None:
        """Use LLM to rerank candidates by relevance to query."""
        from app.layers.agent_core.model_client_manager import model_client_manager
        from app.layers.agent_core.llm_router import llm_router

        model_id = llm_router.MODEL_MAP.get("rerank", "deepseek-chat")
        client, actual_model = await model_client_manager.get_client(model_id)

        # Build reranking prompt
        candidates_text = "\n".join(
            f"[{i+1}] {c.content_text[:200]}"
            for i, c in enumerate(candidates[:20])  # Limit to 20 for prompt size
        )

        prompt = (
            f"请根据查询\"{query}\"对以下记忆片段按相关性重新排序。\n"
            "只输出排序后的编号列表，用逗号分隔，例如：3,1,5,2,4\n"
            "最相关的排在最前面。\n\n"
            f"记忆片段：\n{candidates_text}"
        )

        payload = {
            "model": actual_model,
            "messages": [
                {"role": "system", "content": "你是一个信息检索排序专家，擅长判断文本与查询的相关性。"},
                {"role": "user", "content": prompt},
            ],
            "max_tokens": 256,
            "temperature": 0.1,
        }

        resp = await client.post("/chat/completions", json=payload, timeout=10.0)
        resp.raise_for_status()
        data = resp.json()

        content = data.get("choices", [{}])[0].get("message", {}).get("content", "")

        # Parse ranking from response
        import re
        numbers = re.findall(r'\d+', content)
        if not numbers:
            return None

        # Build reranked list
        reranked: list[SearchResult] = []
        used_indices: set[int] = set()

        for num_str in numbers:
            idx = int(num_str) - 1  # 1-based to 0-based
            if 0 <= idx < len(candidates) and idx not in used_indices:
                reranked.append(candidates[idx])
                used_indices.add(idx)

        # Append any remaining candidates not in the LLM ranking
        for i, c in enumerate(candidates):
            if i not in used_indices:
                reranked.append(c)

        return reranked

    def _heuristic_rerank(
        self,
        candidates: list[SearchResult],
        query: str,
    ) -> list[SearchResult]:
        """Fallback heuristic reranking based on content overlap."""
        query_terms = set(query.lower().split())

        scored: list[tuple[float, SearchResult]] = []
        for candidate in candidates:
            content_terms = set(candidate.content_text.lower().split())
            # Jaccard-like overlap score
            overlap = len(query_terms & content_terms)
            total = len(query_terms | content_terms)
            overlap_score = overlap / total if total > 0 else 0.0

            # Combine with existing fusion score
            combined = 0.6 * candidate.fusion_score + 0.4 * overlap_score
            scored.append((combined, candidate))

        scored.sort(key=lambda x: x[0], reverse=True)
        return [c for _, c in scored]

    def _apply_business_rules(
        self,
        results: list[SearchResult],
    ) -> list[SearchResult]:
        """Apply business rule filtering (Stage 3 of reranking).

        Excludes:
        - Deleted memories (is_deleted=True)
        - Expired memories (expires_at < now)
        - Low confidence memories (confidence < 0.5)
        """
        now = datetime.now(timezone.utc)
        filtered: list[SearchResult] = []

        for result in results:
            metadata = result.metadata

            # Skip deleted
            if metadata.get("is_deleted", False):
                continue

            # Skip expired
            expires_at = metadata.get("expires_at")
            if expires_at:
                try:
                    if isinstance(expires_at, str):
                        from datetime import datetime as dt
                        exp = dt.fromisoformat(expires_at.replace("Z", "+00:00"))
                        if exp < now:
                            continue
                except (ValueError, TypeError):
                    pass

            # Skip low confidence (below retrievable threshold)
            if result.confidence < 0.5:
                continue

            # Skip draft memories
            if metadata.get("is_draft", False):
                continue

            filtered.append(result)

        return filtered

    # ------------------------------------------------------------------
    # Unified search entry point
    # ------------------------------------------------------------------

    async def search(self, request: SearchRequest) -> SearchResponse:
        """Unified search entry point.

        Routes to the appropriate search method based on search_type:
        - "vector": Vector semantic search only
        - "structured": Structured query only
        - "hybrid": Hybrid search (recommended default)
        """
        start_time = time.monotonic()

        if request.search_type == "vector":
            if not request.query_vector:
                return SearchResponse(
                    search_type="vector",
                    search_time_ms=0,
                    results=[],
                    total=0,
                )
            results = await self.vector_search(
                user_id=request.user_id,
                query_vector=request.query_vector,
                memory_type=(
                    request.filters.memory_types[0].value
                    if len(request.filters.memory_types) == 1 else None
                ),
                category=(
                    request.filters.categories[0]
                    if len(request.filters.categories) == 1 else None
                ),
                top_k=request.top_k,
                similarity_threshold=request.similarity_threshold,
            )

        elif request.search_type == "structured":
            results = await self.structured_search(
                user_id=request.user_id,
                filters=request.filters,
                limit=request.top_k,
            )

        else:  # hybrid (default)
            if not request.query_vector:
                # Fall back to structured if no vector available
                results = await self.structured_search(
                    user_id=request.user_id,
                    filters=request.filters,
                    limit=request.top_k,
                )
            else:
                results = await self.hybrid_search(
                    user_id=request.user_id,
                    query=request.query,
                    query_vector=request.query_vector,
                    filters=request.filters,
                    top_k=request.top_k,
                    similarity_threshold=request.similarity_threshold,
                )

        elapsed_ms = int((time.monotonic() - start_time) * 1000)

        return SearchResponse(
            results=results,
            total=len(results),
            search_type=request.search_type,
            search_time_ms=elapsed_ms,
        )

    # ------------------------------------------------------------------
    # Scoring helpers
    # ------------------------------------------------------------------

    def _compute_structured_score(
        self,
        data: dict[str, Any],
        filters: SearchFilters,
    ) -> float:
        """Compute structured match score based on filter criteria.

        Returns a score between 0.0 and 1.0 indicating how well the
        data matches the filter criteria.
        """
        score = 0.0
        max_score = 0.0

        # Confidence match (weight: 0.3)
        max_score += 0.3
        confidence = data.get("confidence", 0.0)
        if filters.min_confidence > 0:
            if confidence >= filters.min_confidence:
                score += 0.3
        else:
            score += 0.3 * confidence

        # Category match (weight: 0.3)
        max_score += 0.3
        if filters.categories:
            if data.get("category", "") in filters.categories:
                score += 0.3
        else:
            score += 0.15  # No filter = partial credit

        # Tag match (weight: 0.2)
        max_score += 0.2
        if filters.tags:
            data_tags = data.get("tags", [])
            matching = len(set(data_tags) & set(filters.tags))
            if matching > 0:
                score += 0.2 * (matching / len(filters.tags))
        else:
            score += 0.1

        # Time range match (weight: 0.2)
        max_score += 0.2
        score += 0.2  # Already filtered by time range, so full credit

        return score / max_score if max_score > 0 else 0.0

    def _compute_time_decay(self, metadata: dict[str, Any]) -> float:
        """Compute time decay score based on memory age.

        Uses exponential decay with configurable half-life.
        More recent memories get higher scores.
        """
        created_at_str = metadata.get("created_at", "")
        if not created_at_str:
            return 0.5  # Default for unknown age

        try:
            if isinstance(created_at_str, str):
                from datetime import datetime as dt
                created_at = dt.fromisoformat(created_at_str.replace("Z", "+00:00"))
            elif isinstance(created_at_str, datetime):
                created_at = created_at_str
            else:
                return 0.5

            now = datetime.now(timezone.utc)
            age_days = (now - created_at).total_seconds() / 86400.0

            # Exponential decay: score = 2^(-age / half_life)
            decay = math.exp(-0.693 * age_days / FusionWeights.TIME_DECAY_HALF_LIFE_DAYS)
            return max(0.0, min(1.0, decay))

        except (ValueError, TypeError):
            return 0.5

    def _compute_fusion_score(self, result: SearchResult) -> float:
        """Compute fusion score per FR-RR-003.

        fusion = alpha * vector_sim + beta * structured_match + gamma * time_decay
        """
        return (
            FusionWeights.ALPHA * result.vector_score
            + FusionWeights.BETA * result.structured_score
            + FusionWeights.GAMMA * result.time_decay_score
        )


# Global singleton
memory_search_engine = MemorySearchEngine()
