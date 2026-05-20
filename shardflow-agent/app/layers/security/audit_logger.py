"""L6 Security Layer: AuditLogger — structured event logging with async buffer."""
import asyncio
import uuid
from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel


class AuditEvent(BaseModel):
    event_id: str
    event_type: str
    timestamp: str
    tenant_id: str
    session_id: str
    task_id: str = ""
    actor: str = "agent"
    details: dict[str, Any] = {}
    severity: str = "INFO"


class AuditLogger:
    def __init__(self, max_buffer: int = 200) -> None:
        self._buffer: asyncio.Queue[AuditEvent] = asyncio.Queue(maxsize=max_buffer)
        self._batch_size: int = 50
        self._flush_interval: float = 5.0
        self._running: bool = False
        self._task: asyncio.Task[Any] | None = None

    def _make_event(self, event_type: str, tenant_id: str, session_id: str,
                    task_id: str = "", details: dict[str, Any] | None = None,
                    severity: str = "INFO") -> AuditEvent:
        return AuditEvent(
            event_id=str(uuid.uuid4()),
            event_type=event_type,
            timestamp=datetime.now(timezone.utc).isoformat(),
            tenant_id=tenant_id,
            session_id=session_id,
            task_id=task_id,
            details=details or {},
            severity=severity,
        )

    async def log(self, event_type: str, tenant_id: str, session_id: str,
                  task_id: str = "", details: dict[str, Any] | None = None,
                  severity: str = "INFO") -> None:
        event = self._make_event(event_type, tenant_id, session_id, task_id, details, severity)
        try:
            self._buffer.put_nowait(event)
        except asyncio.QueueFull:
            pass

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
