"""MemoryWriter — 记忆写入与更新管理器 (FR-WU-001, FR-WU-003).

Manages the memory write pipeline:
- FR-WU-001: Write trigger conditions (session end, explicit confirmation,
  key entity extraction, scheduled task)
- FR-WU-003: Memory compression and summarization (auto-compress memories
  exceeding 512 tokens to 20-30% of original)

Per spec section 4.5:
- Write triggers: session end (P0), explicit confirmation (P0),
  key entity extraction (P1), scheduled task (P2)
- Compression: LLM-powered compression for memories > 512 tokens,
  preserving key entities, removing low-info content
- Compression target: 20-30% of original text
"""
import logging
import uuid
from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, Field

from app.infrastructure.memory_metrics import memory_metrics
from app.infrastructure.milvus_client import insert_memory_vector
from app.layers.agent_core.memory_conflict_resolver import (
    ConflictDetectionResult,
    memory_conflict_resolver,
)
from app.layers.agent_core.memory_orchestrator import memory_orchestrator
from app.layers.security.audit_logger import audit_logger
from app.models.memory import MemoryType

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Write trigger models (FR-WU-001)
# ---------------------------------------------------------------------------

class WriteTrigger:
    """Write trigger types per spec FR-WU-001."""
    SESSION_END = "session_end"                       # P0: Session close
    EXPLICIT_CONFIRMATION = "explicit_confirmation"   # P0: User says "记住这个"
    KEY_ENTITY_EXTRACTION = "key_entity_extraction"   # P1: NER detected
    SCHEDULED_TASK = "scheduled_task"                 # P2: Daily batch archive


class WritePriority:
    """Priority levels for write triggers."""
    P0 = 0  # Critical: session end, explicit confirmation
    P1 = 1  # Important: key entity extraction
    P2 = 2  # Background: scheduled task


TRIGGER_PRIORITY: dict[str, int] = {
    WriteTrigger.SESSION_END: WritePriority.P0,
    WriteTrigger.EXPLICIT_CONFIRMATION: WritePriority.P0,
    WriteTrigger.KEY_ENTITY_EXTRACTION: WritePriority.P1,
    WriteTrigger.SCHEDULED_TASK: WritePriority.P2,
}


class MemoryWriteRequest(BaseModel):
    """Request to write a new memory or update an existing one."""
    user_id: str
    memory_type: MemoryType = MemoryType.SEMANTIC
    category: str = ""                # preference|profile|history|decision|strategy
    content_text: str = ""
    content_structured: dict[str, Any] = Field(default_factory=dict)
    confidence: float = 1.0
    source: str = "conversation"      # conversation|explicit_confirmation|ner_extraction|scheduled_task
    trigger: str = WriteTrigger.KEY_ENTITY_EXTRACTION
    session_id: str = ""
    task_id: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)

    model_config = {"extra": "allow"}


class MemoryWriteResult(BaseModel):
    """Result of a memory write operation."""
    memory_id: str = ""
    status: str = ""                  # created | updated | conflict | rejected
    conflict_detected: bool = False
    conflict_resolution: str = ""
    compressed: bool = False
    original_tokens: int = 0
    compressed_tokens: int = 0
    compression_ratio: float = 0.0
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    model_config = {"extra": "allow"}


# ---------------------------------------------------------------------------
# Compression constants (FR-WU-003)
# ---------------------------------------------------------------------------

class CompressionConfig:
    """Memory compression configuration per spec FR-WU-003."""
    # Trigger: compress when memory text exceeds this token count
    COMPRESSION_THRESHOLD_TOKENS: int = 512
    # Target compression ratio: 20-30% of original
    TARGET_RATIO_MIN: float = 0.20
    TARGET_RATIO_MAX: float = 0.30
    # Maximum content length before forced truncation
    MAX_CONTENT_LENGTH: int = 10000


# ---------------------------------------------------------------------------
# MemoryWriter
# ---------------------------------------------------------------------------

class MemoryWriter:
    """Manages memory write pipeline: trigger evaluation, conflict detection,
    compression, and persistence.

    Usage:
        writer = MemoryWriter()
        result = await writer.write(MemoryWriteRequest(
            user_id="user_001",
            content_text="用户偏好使用官方文档作为首选信息源",
            category="preference",
            confidence=0.95,
            source="explicit_confirmation",
            trigger=WriteTrigger.EXPLICIT_CONFIRMATION,
        ))
    """

    def __init__(self) -> None:
        # Track write statistics
        self._write_stats: dict[str, int] = {
            "total_writes": 0,
            "conflicts_detected": 0,
            "conflicts_resolved": 0,
            "compressions": 0,
            "rejections": 0,
        }

    # ------------------------------------------------------------------
    # FR-WU-001: Write trigger evaluation
    # ------------------------------------------------------------------

    def should_write(
        self,
        trigger: str,
        confidence: float,
        content_text: str,
    ) -> bool:
        """Evaluate whether a write should proceed based on trigger and confidence.

        Per FR-WU-001:
        - Session end (P0): Always write
        - Explicit confirmation (P0): Always write
        - Key entity extraction (P1): Write if confidence >= 0.5
        - Scheduled task (P2): Write if confidence >= 0.7
        """
        priority = TRIGGER_PRIORITY.get(trigger, WritePriority.P2)

        if priority <= WritePriority.P0:
            # P0 triggers always write
            return True
        elif priority == WritePriority.P1:
            # P1: Write if confidence >= 0.5
            return confidence >= 0.5
        else:
            # P2: Write if confidence >= 0.7
            return confidence >= 0.7

    # ------------------------------------------------------------------
    # Main write entry point
    # ------------------------------------------------------------------

    async def write(self, request: MemoryWriteRequest) -> MemoryWriteResult:
        """Execute the full memory write pipeline.

        Pipeline:
        1. Evaluate write trigger (FR-WU-001)
        2. Detect and resolve conflicts (FR-WU-002)
        3. Compress if needed (FR-WU-003)
        4. Persist to L0+L1+L2
        5. Insert vector to Milvus (L3)
        6. Audit log
        """
        self._write_stats["total_writes"] += 1

        # Step 1: Evaluate write trigger
        if not self.should_write(request.trigger, request.confidence, request.content_text):
            self._write_stats["rejections"] += 1
            logger.info(
                "Write rejected: trigger=%s, confidence=%.2f for user %s",
                request.trigger, request.confidence, request.user_id,
            )
            return MemoryWriteResult(
                status="rejected",
                conflict_detected=False,
            )

        # Step 2: Conflict detection and resolution
        conflict_result: ConflictDetectionResult | None = None
        if request.memory_type in (MemoryType.SEMANTIC, MemoryType.EPISODIC):
            conflict_result = await memory_conflict_resolver.detect_and_resolve(
                user_id=request.user_id,
                memory_type=request.memory_type,
                category=request.category,
                new_content=request.content_text,
                new_confidence=request.confidence,
                new_source=request.source,
                session_id=request.session_id,
            )

            if conflict_result.has_conflict:
                self._write_stats["conflicts_detected"] += 1

                if not conflict_result.should_write:
                    self._write_stats["rejections"] += 1
                    logger.info(
                        "Write blocked by conflict resolution: type=%s, resolution=%s",
                        conflict_result.conflict_type,
                        conflict_result.resolution,
                    )
                    return MemoryWriteResult(
                        status="conflict",
                        conflict_detected=True,
                        conflict_resolution=conflict_result.resolution,
                    )

                self._write_stats["conflicts_resolved"] += 1

        # Step 3: Compression (FR-WU-003)
        original_tokens = self._estimate_tokens(request.content_text)
        compressed = False
        compressed_tokens = original_tokens
        compression_ratio = 1.0
        final_content = request.content_text

        if original_tokens > CompressionConfig.COMPRESSION_THRESHOLD_TOKENS:
            compressed_content = await self._compress_content(
                request.content_text, request.category,
            )
            if compressed_content and len(compressed_content) < len(request.content_text):
                final_content = compressed_content
                compressed_tokens = self._estimate_tokens(final_content)
                compression_ratio = compressed_tokens / original_tokens if original_tokens > 0 else 1.0
                compressed = True
                self._write_stats["compressions"] += 1
                memory_metrics.record_compression(original_tokens, compressed_tokens)

                logger.info(
                    "Compressed memory for user %s: %d -> %d tokens (%.1f%%)",
                    request.user_id, original_tokens, compressed_tokens,
                    compression_ratio * 100,
                )

        # Step 4: Persist to L0+L1+L2
        memory_id = f"mem_{uuid.uuid4().hex[:12]}"
        key = memory_id

        data = {
            "memory_id": memory_id,
            "user_id": request.user_id,
            "memory_type": request.memory_type.value,
            "category": request.category,
            "content": {
                "text": final_content,
                "structured": request.content_structured,
            },
            "metadata": {
                "source": request.source,
                "session_id": request.session_id,
                "confidence": request.confidence,
                "created_at": datetime.now(timezone.utc).isoformat(),
                "updated_at": datetime.now(timezone.utc).isoformat(),
                "expires_at": None,
                "version": 1,
                "access_count": 0,
                "last_accessed_at": None,
                "compressed": compressed,
                "original_tokens": original_tokens,
                "compressed_tokens": compressed_tokens,
                "trigger": request.trigger,
                **request.metadata,
            },
            "conflict_info": {
                "has_conflict": conflict_result.has_conflict if conflict_result else False,
                "conflict_with": conflict_result.existing_memory_id if conflict_result and conflict_result.has_conflict else None,
                "resolution_status": conflict_result.resolution if conflict_result and conflict_result.has_conflict else None,
            },
        }

        # Write through orchestrator based on memory type
        if request.memory_type == MemoryType.SEMANTIC:
            await memory_orchestrator.write_semantic(request.user_id, key, data)
        elif request.memory_type == MemoryType.EPISODIC:
            await memory_orchestrator.write_episodic(request.user_id, key, data)
        elif request.memory_type == MemoryType.SESSION_SUMMARY:
            await memory_orchestrator.write_summary(request.user_id, key, data)
        else:
            await memory_orchestrator.write(request.user_id, request.memory_type, key, data)

        # Step 5: Insert vector to Milvus (L3) for semantic/episodic types
        if request.memory_type in (MemoryType.SEMANTIC, MemoryType.EPISODIC):
            await self._insert_vector(
                chunk_id=memory_id,
                user_id=request.user_id,
                memory_type=request.memory_type.value,
                category=request.category,
                content_text=final_content,
                confidence=request.confidence,
            )

        # Step 6: Audit log
        await self._audit_write(request, memory_id, conflict_result)

        result = MemoryWriteResult(
            memory_id=memory_id,
            status="created",
            conflict_detected=conflict_result.has_conflict if conflict_result else False,
            conflict_resolution=(
                conflict_result.resolution if conflict_result and conflict_result.has_conflict else ""
            ),
            compressed=compressed,
            original_tokens=original_tokens,
            compressed_tokens=compressed_tokens,
            compression_ratio=compression_ratio,
        )

        logger.info(
            "Memory written: id=%s, user=%s, type=%s, category=%s, compressed=%s",
            memory_id, request.user_id, request.memory_type.value,
            request.category, compressed,
        )

        return result

    # ------------------------------------------------------------------
    # FR-WU-003: Memory compression and summarization
    # ------------------------------------------------------------------

    async def _compress_content(self, content: str, category: str) -> str | None:
        """Compress memory content using LLM summarization.

        Per FR-WU-003:
        - Trigger: memory text > 512 tokens
        - Strategy: preserve key entities, remove low-info content
        - Use LLM to generate structured summary (Who/What/When/Where/Why)
        - Target compression ratio: 20-30% of original
        """
        if not content or len(content) < 100:
            return content

        # Try LLM-based compression
        try:
            compressed = await self._llm_compress(content, category)
            if compressed:
                return compressed
        except Exception as e:
            logger.warning("LLM compression failed, using fallback: %s", e)

        # Fallback: rule-based compression
        return self._fallback_compress(content)

    async def _llm_compress(self, content: str, category: str) -> str | None:
        """Use LLM to compress memory content."""
        from app.layers.agent_core.model_client_manager import model_client_manager
        from app.layers.agent_core.llm_router import llm_router

        model_id = llm_router.MODEL_MAP.get("compress", "deepseek-chat")
        client, actual_model = await model_client_manager.get_client(model_id)

        prompt = (
            "请将以下记忆内容压缩为简洁的结构化摘要。要求：\n"
            "1. 保留关键实体（人名、地名、时间、数值、技术术语）\n"
            "2. 保留核心结论和关键决策\n"
            "3. 去除寒暄、重复确认等低信息内容\n"
            "4. 压缩率为原始文本的20-30%\n"
            "5. 输出格式：\n"
            "   - 谁/什么(Who/What)：...\n"
            "   - 何时(When)：...\n"
            "   - 何地(Where)：...\n"
            "   - 原因(Why)：...\n"
            "   - 关键结论：...\n"
        )

        if category:
            prompt += f"\n记忆类别：{category}\n"

        prompt += f"\n待压缩内容：\n{content[:3000]}"

        payload = {
            "model": actual_model,
            "messages": [
                {"role": "system", "content": "你是一个记忆压缩专家，擅长提取关键信息并去除冗余内容。"},
                {"role": "user", "content": prompt},
            ],
            "max_tokens": 512,
            "temperature": 0.3,
        }

        resp = await client.post("/chat/completions", json=payload, timeout=15.0)
        resp.raise_for_status()
        data = resp.json()

        choices = data.get("choices", [])
        if choices:
            compressed = choices[0].get("message", {}).get("content", "")
            if compressed and len(compressed) < len(content):
                return compressed

        return None

    def _fallback_compress(self, content: str) -> str:
        """Fallback compression using rule-based extraction."""
        import re

        lines = content.split("\n")
        key_lines: list[str] = []

        # Key indicators for important content
        key_patterns = [
            r"确认", r"结论", r"决定", r"偏好", r"排除",
            r"待办", r"重要", r"关键", r"必须", r"注意",
            r"confirmed", r"conclusion", r"decision", r"preference",
            r"important", r"key", r"must", r"note",
        ]

        for line in lines:
            line = line.strip()
            if not line:
                continue

            # Check if line contains key information
            if any(re.search(p, line, re.IGNORECASE) for p in key_patterns):
                key_lines.append(line)

        if not key_lines:
            # Take first 25% of lines as summary
            keep_count = max(1, len(lines) // 4)
            key_lines = lines[:keep_count]

        compressed = "\n".join(key_lines)

        # Ensure we don't exceed the target ratio
        target_length = int(len(content) * CompressionConfig.TARGET_RATIO_MAX)
        if len(compressed) > target_length:
            compressed = compressed[:target_length] + "..."

        return compressed

    # ------------------------------------------------------------------
    # Vector insertion helper
    # ------------------------------------------------------------------

    async def _insert_vector(
        self,
        chunk_id: str,
        user_id: str,
        memory_type: str,
        category: str,
        content_text: str,
        confidence: float,
    ) -> None:
        """Insert memory vector into Milvus for semantic retrieval.

        Generates embedding from content text and inserts into memory_vectors collection.
        """
        try:
            # Generate embedding vector
            embedding = await self._generate_embedding(content_text)
            if not embedding:
                logger.warning("No embedding generated for memory %s, skipping vector insert", chunk_id)
                return

            success = await insert_memory_vector(
                chunk_id=chunk_id,
                user_id=user_id,
                memory_type=memory_type,
                category=category,
                content_vector=embedding,
                content_text=content_text[:65535],  # Milvus VARCHAR limit
                confidence=confidence,
            )

            if success:
                logger.debug("Vector inserted for memory %s", chunk_id)
            else:
                logger.warning("Failed to insert vector for memory %s", chunk_id)

        except Exception as e:
            logger.warning("Vector insertion failed for memory %s: %s", chunk_id, e)

    async def _generate_embedding(self, text: str) -> list[float]:
        """Generate embedding vector for text content.

        Uses the configured embedding model. Falls back to empty vector
        if embedding generation fails.
        """
        try:
            from app.layers.agent_core.model_client_manager import model_client_manager
            from app.layers.agent_core.llm_router import llm_router

            model_id = llm_router.MODEL_MAP.get("embedding", "text-embedding-3-small")
            client, actual_model = await model_client_manager.get_client(model_id)

            payload = {
                "model": actual_model,
                "input": text[:8000],  # Truncate for embedding API limits
            }

            resp = await client.post("/embeddings", json=payload, timeout=10.0)
            resp.raise_for_status()
            data = resp.json()

            embeddings = data.get("data", [])
            if embeddings:
                return embeddings[0].get("embedding", [])

        except Exception as e:
            logger.warning("Embedding generation failed: %s", e)

        return []

    # ------------------------------------------------------------------
    # Audit logging
    # ------------------------------------------------------------------

    async def _audit_write(
        self,
        request: MemoryWriteRequest,
        memory_id: str,
        conflict_result: ConflictDetectionResult | None,
    ) -> None:
        """Log memory write operation to audit system."""
        try:
            details: dict[str, Any] = {
                "memory_id": memory_id,
                "memory_type": request.memory_type.value,
                "category": request.category,
                "confidence": request.confidence,
                "source": request.source,
                "trigger": request.trigger,
                "content_length": len(request.content_text),
            }

            if conflict_result and conflict_result.has_conflict:
                details["conflict_type"] = conflict_result.conflict_type
                details["conflict_resolution"] = conflict_result.resolution

            await audit_logger.log(
                event_type="memory_write",
                user_id=request.user_id,
                session_id=request.session_id,
                task_id=request.task_id,
                details=details,
                severity="INFO",
            )
        except Exception as e:
            logger.warning("Failed to audit memory write: %s", e)

    # ------------------------------------------------------------------
    # Token estimation
    # ------------------------------------------------------------------

    def _estimate_tokens(self, text: str) -> int:
        """Estimate token count for text."""
        if not text:
            return 0
        return len(text) // 3  # Conservative for mixed CJK/English

    # ------------------------------------------------------------------
    # Batch write for session archiving
    # ------------------------------------------------------------------

    async def batch_write(
        self,
        requests: list[MemoryWriteRequest],
    ) -> list[MemoryWriteResult]:
        """Batch write multiple memory entries.

        Used for session-end archiving where multiple memories
        (summary, semantic, episodic) are written together.
        """
        results: list[MemoryWriteResult] = []

        for request in requests:
            try:
                result = await self.write(request)
                results.append(result)
            except Exception as e:
                logger.error("Batch write failed for user %s: %s", request.user_id, e)
                results.append(MemoryWriteResult(
                    status="error",
                    conflict_detected=False,
                ))

        logger.info(
            "Batch write completed: %d/%d successful",
            sum(1 for r in results if r.status == "created"),
            len(results),
        )

        return results

    # ------------------------------------------------------------------
    # Statistics
    # ------------------------------------------------------------------

    def get_stats(self) -> dict[str, int]:
        """Get write statistics."""
        return dict(self._write_stats)


# Global singleton
memory_writer = MemoryWriter()
