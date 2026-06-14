import asyncio
import logging
from collections import deque
from typing import Any

import httpx

from app.config import settings

logger = logging.getLogger(__name__)


class CallbackClient:
    def __init__(self) -> None:
        self._base_url = settings.java_base_url
        self._client: httpx.AsyncClient | None = None
        self._audit_buffer: deque[dict[str, Any]] = deque(maxlen=1000)
        self._retry_task: asyncio.Task | None = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                base_url=self._base_url,
                timeout=httpx.Timeout(30.0),
                headers={
                    "X-API-Key": settings.java_api_key or settings.llm_api_key,
                    "Content-Type": "application/json",
                },
            )
        return self._client

    async def _ensure_retry_task(self) -> None:
        """确保重试任务已启动。"""
        if self._retry_task is None or self._retry_task.done():
            self._retry_task = asyncio.create_task(self._retry_buffered_audits())

    async def session_complete(self, session_data: dict[str, Any]) -> dict[str, Any]:
        client = await self._get_client()
        resp = await client.post("/api/v1/callback/sessions/complete", json=session_data)
        resp.raise_for_status()
        return dict(resp.json())

    async def write_audit(self, audit_data: dict[str, Any]) -> dict[str, Any]:
        client = await self._get_client()
        resp = await client.post("/api/v1/callback/audit", json=audit_data)
        resp.raise_for_status()
        return dict(resp.json())

    async def report_progress(self, progress_data: dict[str, Any]) -> dict[str, Any]:
        client = await self._get_client()
        resp = await client.post("/api/v1/callback/progress", json=progress_data)
        resp.raise_for_status()
        return dict(resp.json())

    async def save_strategy(self, strategy_data: dict[str, Any]) -> dict[str, Any]:
        client = await self._get_client()
        resp = await client.post("/api/v1/strategies/callback", json=strategy_data)
        resp.raise_for_status()
        return dict(resp.json())

    async def save_strategy_record(self, strategy_data: dict[str, Any]) -> dict[str, Any]:
        """Save a strategy record via the new P6 callback endpoint.

        Calls POST /api/v1/callback/strategies for strategy_records table persistence.
        Per P6.2.3: Callback interface for strategy persistence.
        """
        client = await self._get_client()
        resp = await client.post("/api/v1/callback/strategies", json=strategy_data)
        resp.raise_for_status()
        return dict(resp.json())

    async def save_strategy_feedback(self, feedback_data: dict[str, Any]) -> dict[str, Any]:
        """Save strategy feedback via callback endpoint.

        Calls POST /api/v1/strategy/feedback for updating success_score.
        Per FR-SR-001: User feedback loop.
        """
        client = await self._get_client()
        resp = await client.post("/api/v1/strategy/feedback", json=feedback_data)
        resp.raise_for_status()
        return dict(resp.json())

    async def delete_strategy(self, delete_data: dict[str, Any]) -> dict[str, Any]:
        """Delete a strategy record via callback endpoint.

        Calls DELETE /api/v1/strategy/{recordId} for logical deletion.
        """
        client = await self._get_client()
        record_id = delete_data.get("record_id", "")
        resp = await client.delete(f"/api/v1/strategy/{record_id}")
        resp.raise_for_status()
        return dict(resp.json())

    async def write_mcp_audit(self, audit_data: dict[str, Any]) -> dict[str, Any]:
        """MCP 工具调用审计回调（FR-INVOKE-005）。

        Calls POST /api/v1/callback/mcp/audit for MCP tool call audit logging.
        Per spec section 5.4: Python 推理层回调 Java 端记录审计日志。
        失败时缓冲到本地，定时重试发送（SEC-AUDIT-002）。
        """
        try:
            client = await self._get_client()
            resp = await client.post("/api/v1/callback/mcp/audit", json=audit_data, timeout=10.0)
            resp.raise_for_status()
            return dict(resp.json())
        except Exception as e:
            logger.warning(f"Failed to send MCP audit log, buffering: {e}")
            self._audit_buffer.append(audit_data)
            await self._ensure_retry_task()
            return {"status": "buffered"}

    async def _retry_buffered_audits(self) -> None:
        """定时重试缓冲的审计日志（SEC-AUDIT-002）。"""
        while True:
            await asyncio.sleep(30)
            if not self._audit_buffer:
                continue
            client = await self._get_client()
            retry_count = 0
            max_retries = len(self._audit_buffer)
            while self._audit_buffer and retry_count < max_retries:
                audit_data = self._audit_buffer[0]
                try:
                    resp = await client.post(
                        "/api/v1/callback/mcp/audit", json=audit_data, timeout=10.0
                    )
                    resp.raise_for_status()
                    self._audit_buffer.popleft()
                except Exception:
                    break  # 仍然失败，等待下次重试
                retry_count += 1

    async def close(self) -> None:
        if self._retry_task and not self._retry_task.done():
            self._retry_task.cancel()
        if self._client:
            await self._client.aclose()
            self._client = None


callback_client = CallbackClient()
