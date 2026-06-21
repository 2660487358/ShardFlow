"""CompositeAdapter — L0→L1→L2 degrade-read + write-broadcast adapter.

Implements the four-tier memory architecture:
- Read:  L0 (local) → L1 (Redis) → L2 (Java API), backfilling on hit
- Write: Broadcast to L2 (authoritative) + L1 (cache) + L0 (local)

Memory types and their tier routing:
- SHORT_TERM:      L0 + L1 only (ephemeral session data)
- SESSION_SUMMARY: L0 + L1 + L2 (cross-session state snapshots)
- SEMANTIC:        L0 + L1 + L2 (user facts and preferences)
- EPISODIC:        L0 + L1 + L2 (decision paths and events)

S3.1: L2 read/write paths are protected by MemoryCircuitBreaker. When the
circuit is open or an L2 operation fails, writes are buffered to the
degradation queue and reads fall back to L1/L0 results.
"""
import logging
from datetime import datetime, timezone
from typing import Any

from app.infrastructure.memory_metrics import memory_metrics
from app.models.memory import MemoryRecord, MemoryQuery, MemoryType
from ..memory_circuit_breaker import get_memory_circuit_breaker
from .l0_adapter import L0CacheAdapter
from .redis_adapter import RedisAdapter
from .java_adapter import JavaAPIAdapter

logger = logging.getLogger(__name__)


async def _generate_memory_embedding(content_text: str) -> list[float] | None:
    """Generate embedding for a memory content string.

    Falls back to None if the embedding service is unavailable.
    Enhanced diagnostics: logs full response body when embedding extraction fails
    so that LiteLLM proxy response-format drift can be detected quickly.
    """
    try:
        from app.layers.agent_core.model_client_manager import model_client_manager
        from app.layers.agent_core.llm_router import llm_router

        model_id = llm_router.MODEL_MAP.get("embedding", "text-embedding-3-small")
        client, actual_model = await model_client_manager.get_client(model_id)
        payload = {"model": actual_model, "input": content_text[:8000]}
        resp = await client.post("/embeddings", json=payload, timeout=10.0)
        resp.raise_for_status()
        data = resp.json()
        embeddings = data.get("data", [])
        if embeddings:
            # Check if embedding field exists and is non-None
            embedding = embeddings[0].get("embedding")
            if embedding is not None:
                return embedding
            # embedding is None but data exists — log the raw structure for diagnosis
            logger.warning(
                "Embedding data[0].embedding is None: model=%s, keys_in_data0=%s, "
                "full_data_sample=%s",
                actual_model,
                list(embeddings[0].keys()) if isinstance(embeddings[0], dict) else type(embeddings[0]),
                str(data)[:500],
            )
        else:
            logger.warning(
                "Embedding response missing 'data' array: model=%s, top_keys=%s, "
                "response_sample=%s",
                actual_model,
                list(data.keys())[:10] if isinstance(data, dict) else type(data),
                str(data)[:500],
            )
    except Exception as e:
        logger.warning("Failed to generate memory embedding: %s", e)
    return None


def _extract_content_text(data: dict[str, Any]) -> str:
    """Extract the textual content from memory data for embedding.

    Handles multiple memory data shapes:
    - Semantic: {"text": "..."}
    - Episodic chunk: {"content": {"text": "...", "structured": {...}}}
    - Episodic raw (DecisionPath dump): {"steps": [...], "final_conclusion": "..."}
    - Summary: {"summary": "..."}
    """
    if not isinstance(data, dict):
        return ""
    # Semantic memories use "text" directly
    if isinstance(data.get("text"), str) and data["text"]:
        return data["text"]
    # JavaAdapter normalizes content into {"text": ..., "structured": ...}
    content = data.get("content")
    if isinstance(content, dict) and isinstance(content.get("text"), str) and content["text"]:
        return content["text"]
    # Episodic raw (DecisionPath model dump): extract from steps + final_conclusion
    if isinstance(data.get("steps"), list):
        parts: list[str] = []
        for step in data["steps"]:
            if isinstance(step, dict) and step.get("content"):
                parts.append(step["content"][:500])
        if data.get("final_conclusion"):
            parts.append(data["final_conclusion"][:500])
        if parts:
            return "\n".join(parts)
    # Episodic / session summary may have a summary field
    if isinstance(data.get("summary"), str) and data["summary"]:
        return data["summary"]
    return ""


class CompositeAdapter:
    """Three-tier composite: L0 (sub-ms) → L1 (ms) → L2 (ms-to-Java).

    Supports four-layer memory model routing:
    - SHORT_TERM: L0 + L1 only
    - SESSION_SUMMARY / SEMANTIC / EPISODIC: full L0 → L1 → L2 chain
    """

    def __init__(self, use_l2: bool = True) -> None:
        self._l0 = L0CacheAdapter(max_size=256)
        self._l1 = RedisAdapter()
        self._l2 = JavaAPIAdapter() if use_l2 else None
        self._circuit_breaker = get_memory_circuit_breaker()

    def _should_use_l2(self, memory_type: MemoryType) -> bool:
        return memory_type != MemoryType.SHORT_TERM and self._l2 is not None

    # ------------------------------------------------------------------
    # Read with degrade + backfill
    # ------------------------------------------------------------------

    async def read(self, user_id: str, memory_type: MemoryType, key: str) -> MemoryRecord | None:
        # L0: local LRU (< 0.1ms)
        record = await self._l0.read(user_id, memory_type, key)
        if record is not None:
            memory_metrics.record_hit("L0")
            return record
        memory_metrics.record_miss("L0")

        # L1: Redis (< 2ms)
        record = await self._l1.read(user_id, memory_type, key)
        if record is not None:
            memory_metrics.record_hit("L1")
            await self._l0.write(user_id, memory_type, key, record.data, record.ttl_seconds)
            return record
        memory_metrics.record_miss("L1")

        # L2: Java API (< 50ms) — only for non-ephemeral types, protected by circuit breaker
        if self._should_use_l2(memory_type):
            l2_record = await self._circuit_breaker.call(
                self._l2.read, user_id, memory_type, key, fallback=None
            )
            if l2_record is not None:
                memory_metrics.record_hit("L2")
                await self._l1.write(user_id, memory_type, key, l2_record.data, l2_record.ttl_seconds)
                await self._l0.write(user_id, memory_type, key, l2_record.data, l2_record.ttl_seconds)
                return l2_record
            memory_metrics.record_miss("L2")

        return None

    # ------------------------------------------------------------------
    # Write broadcast (L2 authoritative → L1 cache → L0 local)
    # ------------------------------------------------------------------

    async def write(self, user_id: str, memory_type: MemoryType, key: str,
                    data: dict[str, Any], ttl_seconds: int = 0) -> MemoryRecord:
        now = datetime.now(timezone.utc)

        # L2: authoritative write — protected by circuit breaker; buffer failures for retry
        if self._should_use_l2(memory_type):
            l2_record = await self._circuit_breaker.call(
                self._l2.write, user_id, memory_type, key, data, ttl_seconds, fallback=None
            )
            if l2_record is None:
                # Circuit open or L2 failure — buffer to degradation queue for retry
                logger.info(
                    "L2 write skipped/failed for %s/%s, buffering to degradation queue",
                    memory_type.value, key,
                )
                from app.layers.agent_core.memory_degradation import memory_degradation
                await memory_degradation.buffer_write(
                    user_id, memory_type.value, key, data
                )

        # L1: Redis cache
        try:
            await self._l1.write(user_id, memory_type, key, data, ttl_seconds)
        except Exception as e:
            logger.warning("L1 write failed: %s", e)

        # L0: update local cache immediately
        record = await self._l0.write(user_id, memory_type, key, data, ttl_seconds)

        # FIX: ensure semantic/episodic memories have vectors in Milvus so that
        # MemorySearchEngine.vector_search can retrieve them by similarity.
        if self._should_use_l2(memory_type) and memory_type in (MemoryType.SEMANTIC, MemoryType.EPISODIC):
            try:
                content_text = _extract_content_text(data)
                if content_text:
                    from app.infrastructure.milvus_client import insert_memory_vector
                    embedding = await _generate_memory_embedding(content_text)
                    if embedding:
                        await insert_memory_vector(
                            chunk_id=key,
                            user_id=user_id,
                            memory_type=memory_type.value,
                            category=data.get("category", "general"),
                            content_vector=embedding,
                            content_text=content_text,
                            confidence=data.get("confidence", 1.0),
                        )
                        logger.info(
                            "[COMPOSITE_WRITE_VECTOR] inserted user=%s type=%s key=%s content_len=%d",
                            user_id, memory_type.value, key, len(content_text),
                        )
                    else:
                        logger.warning(
                            "[COMPOSITE_WRITE_VECTOR] no embedding user=%s type=%s key=%s",
                            user_id, memory_type.value, key,
                        )
                else:
                    logger.warning(
                        "[COMPOSITE_WRITE_VECTOR] empty content_text user=%s type=%s key=%s",
                        user_id, memory_type.value, key,
                    )
            except Exception as e:
                logger.warning("[COMPOSITE_WRITE_VECTOR] failed for %s/%s: %s", memory_type.value, key, e)

        return record

    # ------------------------------------------------------------------
    # Delete: cascade through all tiers
    # ------------------------------------------------------------------

    async def delete(self, user_id: str, memory_type: MemoryType, key: str) -> bool:
        deleted = False
        if await self._l0.delete(user_id, memory_type, key):
            deleted = True
        if await self._l1.delete(user_id, memory_type, key):
            deleted = True
        if self._should_use_l2(memory_type):
            l2_deleted = await self._circuit_breaker.call(
                self._l2.delete, user_id, memory_type, key, fallback=False
            )
            if l2_deleted:
                deleted = True
        return deleted

    # ------------------------------------------------------------------
    # Search: route by memory type
    # ------------------------------------------------------------------

    async def search(self, user_id: str, memory_type: MemoryType,
                     query: MemoryQuery) -> list[MemoryRecord]:
        # For SEMANTIC/EPISODIC, prefer L2 (structured + vector search) — protected by circuit breaker
        if memory_type in (MemoryType.SEMANTIC, MemoryType.EPISODIC) and self._should_use_l2(memory_type):
            results = await self._circuit_breaker.call(
                self._l2.search, user_id, memory_type, query, fallback=[]
            )
            if results:
                return results

        # For SESSION_SUMMARY/SHORT_TERM, search L1 (Redis) — use optimized pipeline search
        results = await self._l1.search_optimized(user_id, memory_type, query)
        if not results:
            results = await self._l0.search(user_id, memory_type, query)
        return results

    async def exists(self, user_id: str, memory_type: MemoryType, key: str) -> bool:
        if await self._l0.exists(user_id, memory_type, key):
            return True
        record = await self.read(user_id, memory_type, key)
        return record is not None
