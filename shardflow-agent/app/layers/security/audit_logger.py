"""L6 Security Layer: AuditLogger — structured event logging with async buffer.

Enhanced per FR-EM-003: Full-chain traceability & audit.
- Memory operation audit coverage (memory_read, memory_write, memory_delete, memory_search)
- Structured audit event schema aligned with spec section 9.4
- Query text desensitization for L3/L4 data (PII masking)
- 180-day retention enforced on Java side (P4.2.6)
"""
import asyncio
import logging
import re
import uuid
from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel

logger = logging.getLogger(__name__)


class AuditEvent(BaseModel):
    event_id: str
    event_type: str
    timestamp: str
    user_id: str
    session_id: str
    task_id: str = ""
    actor: str = "agent"
    details: dict[str, Any] = {}
    severity: str = "INFO"


# ---------------------------------------------------------------------------
# Memory audit event types (per spec section 9.4)
# ---------------------------------------------------------------------------

MEMORY_AUDIT_OPS = {
    "memory_read",
    "memory_write",
    "memory_delete",
    "memory_search",
    "episodic_write",
    "episodic_read",
    "trace_save",
    "trace_read",
}

# PII patterns for desensitization in audit logs
_PII_PATTERNS = [
    (re.compile(r'\b1[3-9]\d{9}\b'), lambda m: m.group()[:3] + "****" + m.group()[-4:]),      # 手机号
    (re.compile(r'\b\d{17}[\dXx]\b'), lambda m: m.group()[:4] + "**********" + m.group()[-4:]), # 身份证
    (re.compile(r'\b[\w.+-]+@[\w-]+\.[\w.]+\b'), lambda m: m.group()[0] + "***@" + m.group().split("@")[1]),  # 邮箱
]


class AuditLogger:
    def __init__(self, max_buffer: int = 200) -> None:
        self._buffer: asyncio.Queue[AuditEvent] = asyncio.Queue(maxsize=max_buffer)
        self._batch_size: int = 50
        self._flush_interval: float = 5.0
        self._running: bool = False
        self._task: asyncio.Task[Any] | None = None
        # Track memory operation stats for monitoring
        self._memory_op_counts: dict[str, int] = {}

    def _make_event(self, event_type: str, user_id: str, session_id: str,
                    task_id: str = "", details: dict[str, Any] | None = None,
                    severity: str = "INFO") -> AuditEvent:
        return AuditEvent(
            event_id=str(uuid.uuid4()),
            event_type=event_type,
            timestamp=datetime.now(timezone.utc).isoformat(),
            user_id=user_id,
            session_id=session_id,
            task_id=task_id,
            details=details or {},
            severity=severity,
        )

    async def log(self, event_type: str, user_id: str, session_id: str,
                  task_id: str = "", details: dict[str, Any] | None = None,
                  severity: str = "INFO") -> None:
        event = self._make_event(event_type, user_id, session_id, task_id, details, severity)

        # Track memory operation counts
        if event_type in MEMORY_AUDIT_OPS:
            self._memory_op_counts[event_type] = self._memory_op_counts.get(event_type, 0) + 1

        try:
            self._buffer.put_nowait(event)
        except asyncio.QueueFull:
            # Degradation: write to Redis dead-letter queue instead of silently dropping
            try:
                from app.infrastructure.redis_client import redis_client
                import json
                r = await redis_client.get_redis()
                await r.rpush(
                    f"shardflow:audit:dead_letter:{user_id}",
                    json.dumps(event.model_dump(), ensure_ascii=False),
                )
            except Exception:
                pass  # Last resort: nothing else we can do

    # ------------------------------------------------------------------
    # Memory audit convenience methods (FR-EM-003)
    # ------------------------------------------------------------------

    async def log_memory_read(self, user_id: str, session_id: str,
                               memory_id: str, memory_type: str = "",
                               task_id: str = "") -> None:
        """Audit log for memory read operations (per spec 9.4)."""
        await self.log(
            event_type="memory_read",
            user_id=user_id,
            session_id=session_id,
            task_id=task_id,
            details={
                "target_memory_id": memory_id,
                "memory_type": memory_type,
            },
        )

    async def log_memory_write(self, user_id: str, session_id: str,
                                memory_id: str, memory_type: str = "",
                                category: str = "", confidence: float = 0.0,
                                conflict_detected: bool = False,
                                task_id: str = "") -> None:
        """Audit log for memory write operations (per spec 9.4)."""
        await self.log(
            event_type="memory_write",
            user_id=user_id,
            session_id=session_id,
            task_id=task_id,
            details={
                "target_memory_id": memory_id,
                "memory_type": memory_type,
                "category": category,
                "confidence": confidence,
                "conflict_detected": conflict_detected,
            },
        )

    async def log_memory_delete(self, user_id: str, session_id: str,
                                 memory_id: str, memory_type: str = "",
                                 task_id: str = "") -> None:
        """Audit log for memory delete operations (per spec 9.4)."""
        await self.log(
            event_type="memory_delete",
            user_id=user_id,
            session_id=session_id,
            task_id=task_id,
            details={
                "target_memory_id": memory_id,
                "memory_type": memory_type,
            },
        )

    async def log_memory_search(self, user_id: str, session_id: str,
                                 query_text: str, result_ids: list[str] | None = None,
                                 search_type: str = "", task_id: str = "") -> None:
        """Audit log for memory search operations (per spec 9.4).

        Query text is desensitized for PII before logging.
        """
        desensitized_query = self._desensitize_text(query_text)
        await self.log(
            event_type="memory_search",
            user_id=user_id,
            session_id=session_id,
            task_id=task_id,
            details={
                "query_text": desensitized_query,
                "retrieved_memory_ids": result_ids or [],
                "search_type": search_type,
            },
        )

    # ------------------------------------------------------------------
    # PII desensitization (per spec 9.3)
    # ------------------------------------------------------------------

    def _desensitize_text(self, text: str) -> str:
        """Desensitize PII in text for audit logging.

        Applies masking rules per spec section 9.3:
        - Phone: first 3 + **** + last 4
        - ID card: first 4 + ********** + last 4
        - Email: first char + ***@ + domain
        """
        result = text
        for pattern, replacer in _PII_PATTERNS:
            result = pattern.sub(replacer, result)
        return result

    # ------------------------------------------------------------------
    # Monitoring helpers
    # ------------------------------------------------------------------

    def get_memory_op_stats(self) -> dict[str, int]:
        """Get memory operation audit counts for monitoring."""
        return dict(self._memory_op_counts)

    def reset_memory_op_stats(self) -> None:
        """Reset memory operation audit counts."""
        self._memory_op_counts.clear()

    # ------------------------------------------------------------------
    # Background flush (unchanged)
    # ------------------------------------------------------------------

    async def start_background_flush(self) -> None:
        self._running = True
        self._task = asyncio.create_task(self._flush_loop())

    async def stop_background_flush(self) -> None:
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

    async def _flush_loop(self) -> None:
        while self._running:
            await asyncio.sleep(self._flush_interval)
            await self._flush_batch()

    async def _flush_batch(self) -> None:
        batch: list[AuditEvent] = []
        for _ in range(self._batch_size):
            if self._buffer.empty():
                break
            try:
                event = self._buffer.get_nowait()
                batch.append(event)
            except asyncio.QueueEmpty:
                break

        if not batch:
            return

        try:
            from app.infrastructure.callback_client import callback_client
            for event in batch:
                await callback_client.write_audit(event.model_dump())
        except Exception:
            for event in batch:
                try:
                    self._buffer.put_nowait(event)
                except asyncio.QueueFull:
                    pass

    def get_event_count(self) -> int:
        return self._buffer.qsize()


audit_logger = AuditLogger()
