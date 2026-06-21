import asyncio
import logging
import uuid as _uuid
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

    def _build_idempotency_headers(
        self,
        request_id: str | None = None,
        trace_id: str | None = None,
        payload: dict[str, Any] | None = None,
    ) -> dict[str, str]:
        """S3.10/G-2: 构建幂等头部 X-Request-ID + X-Trace-ID。

        优先级：显式参数 > payload 中的字段 > 自动生成。

        Args:
            request_id: 显式幂等键，不传则从 payload.idempotency_key/request_id 提取或自动生成
            trace_id: 显式链路追踪 ID，不传则从 payload.trace_id 提取或自动生成
            payload: 可选的负载数据，用于提取已有的 idempotency_key/trace_id

        Returns:
            包含 X-Request-ID 和 X-Trace-ID 的 headers dict
        """
        if request_id is None and payload:
            request_id = payload.get("idempotency_key") or payload.get("request_id")
        if trace_id is None and payload:
            trace_id = payload.get("trace_id")

        if request_id is None:
            request_id = f"req_{_uuid.uuid4().hex[:16]}"
        if trace_id is None:
            trace_id = f"trace_{_uuid.uuid4().hex[:16]}"

        return {
            "X-Request-ID": request_id,
            "X-Trace-ID": trace_id,
        }

    async def _ensure_retry_task(self) -> None:
        """确保重试任务已启动。"""
        if self._retry_task is None or self._retry_task.done():
            self._retry_task = asyncio.create_task(self._retry_buffered_audits())

    async def session_complete(
        self,
        session_data: dict[str, Any],
        request_id: str | None = None,
        trace_id: str | None = None,
    ) -> dict[str, Any]:
        """CB-01 会话完成回调（G-2 幂等）。"""
        client = await self._get_client()
        headers = self._build_idempotency_headers(request_id, trace_id, session_data)
        resp = await client.post(
            "/api/v1/callback/sessions/complete", json=session_data, headers=headers
        )
        resp.raise_for_status()
        return dict(resp.json())

    async def write_audit(
        self,
        audit_data: dict[str, Any],
        request_id: str | None = None,
        trace_id: str | None = None,
    ) -> dict[str, Any]:
        """CB-02 审计日志回调（G-2 幂等）。"""
        client = await self._get_client()
        headers = self._build_idempotency_headers(request_id, trace_id, audit_data)
        resp = await client.post(
            "/api/v1/callback/audit", json=audit_data, headers=headers
        )
        resp.raise_for_status()
        return dict(resp.json())

    async def report_progress(
        self,
        progress_data: dict[str, Any],
        request_id: str | None = None,
        trace_id: str | None = None,
    ) -> dict[str, Any]:
        """CB-03 进度上报回调（G-2 幂等）。"""
        client = await self._get_client()
        headers = self._build_idempotency_headers(request_id, trace_id, progress_data)
        resp = await client.post(
            "/api/v1/callback/progress", json=progress_data, headers=headers
        )
        resp.raise_for_status()
        return dict(resp.json())

    async def save_strategy(
        self,
        strategy_data: dict[str, Any],
        request_id: str | None = None,
        trace_id: str | None = None,
    ) -> dict[str, Any]:
        """CB-04 策略记录回调（G-2/G-5 幂等）。"""
        client = await self._get_client()
        headers = self._build_idempotency_headers(request_id, trace_id, strategy_data)
        resp = await client.post(
            "/api/v1/strategies/callback", json=strategy_data, headers=headers
        )
        resp.raise_for_status()
        return dict(resp.json())

    async def save_strategy_record(
        self,
        strategy_data: dict[str, Any],
        request_id: str | None = None,
        trace_id: str | None = None,
    ) -> dict[str, Any]:
        """CB-12 策略保存回调（G-2/G-5 幂等）。

        Calls POST /api/v1/callback/strategies for strategy_records table persistence.
        Per P6.2.3: Callback interface for strategy persistence.
        """
        client = await self._get_client()
        headers = self._build_idempotency_headers(request_id, trace_id, strategy_data)
        resp = await client.post(
            "/api/v1/callback/strategies", json=strategy_data, headers=headers
        )
        resp.raise_for_status()
        return dict(resp.json())

    async def save_strategy_feedback(
        self,
        feedback_data: dict[str, Any],
        request_id: str | None = None,
        trace_id: str | None = None,
    ) -> dict[str, Any]:
        """CB-05 策略反馈回调（G-5 幂等）。

        Calls POST /api/v1/strategy/feedback for updating success_score.
        Per FR-SR-001: User feedback loop.
        """
        client = await self._get_client()
        headers = self._build_idempotency_headers(request_id, trace_id, feedback_data)
        resp = await client.post(
            "/api/v1/strategy/feedback", json=feedback_data, headers=headers
        )
        resp.raise_for_status()
        return dict(resp.json())

    async def delete_strategy(
        self,
        delete_data: dict[str, Any],
        request_id: str | None = None,
        trace_id: str | None = None,
    ) -> dict[str, Any]:
        """CB-11 策略删除回调（G-5 幂等）。

        Calls DELETE /api/v1/strategy/{recordId} for logical deletion.
        """
        client = await self._get_client()
        headers = self._build_idempotency_headers(request_id, trace_id, delete_data)
        record_id = delete_data.get("record_id", "")
        resp = await client.delete(
            f"/api/v1/strategy/{record_id}", headers=headers
        )
        resp.raise_for_status()
        return dict(resp.json())

    async def write_mcp_audit(
        self,
        audit_data: dict[str, Any],
        request_id: str | None = None,
        trace_id: str | None = None,
    ) -> dict[str, Any]:
        """MCP 工具调用审计回调（FR-INVOKE-005 / CB-10）。

        Calls POST /api/v1/callback/mcp/audit for MCP tool call audit logging.
        Per Python-Java接口契约文档 §2.5:
        - Headers: X-Request-ID, X-Trace-ID, Authorization
        - 幂等: 按 X-Request-ID 去重
        - 规则条款: C-3.8, C-5.8, C-9.6, C-10.11

        失败时缓冲到本地，定时重试发送（SEC-AUDIT-002）。

        Args:
            audit_data: 审计数据 dict
            request_id: 幂等键（X-Request-ID），不传则从 audit_data.idempotency_key 提取或自动生成
            trace_id: 链路追踪 ID（X-Trace-ID），不传则从 audit_data.trace_id 提取或自动生成
        """
        import uuid as _uuid

        # S3.7/S3.10: 幂等键优先级：参数 > audit_data.idempotency_key > 自动生成
        if request_id is None:
            request_id = audit_data.get("idempotency_key") or f"req_{_uuid.uuid4().hex[:16]}"
        if trace_id is None:
            trace_id = audit_data.get("trace_id") or f"trace_{_uuid.uuid4().hex[:16]}"

        try:
            client = await self._get_client()
            resp = await client.post(
                "/api/v1/callback/mcp/audit",
                json=audit_data,
                headers={
                    "X-Request-ID": request_id,
                    "X-Trace-ID": trace_id,
                },
                timeout=10.0,
            )
            resp.raise_for_status()
            return dict(resp.json())
        except Exception as e:
            logger.warning(f"Failed to send MCP audit log, buffering: {e}")
            self._audit_buffer.append(audit_data)
            await self._ensure_retry_task()
            return {"status": "buffered"}

    async def session_summary_callback(
        self,
        session_id: str,
        user_id: str,
        summary: str,
        version: int,
        token_count: int = 0,
        trigger_reason: str = "session_end",
        request_id: str | None = None,
        trace_id: str | None = None,
    ) -> dict[str, Any]:
        """CB-09 会话摘要回调：Python 生成摘要后回调 Java 异步归档 PG（DF-3 步骤⑤）。

        Per Python-Java接口契约文档 §2.4:
        - POST /api/v1/callback/session-summary
        - Headers: X-Request-ID, X-Trace-ID, Authorization
        - 幂等: 按 X-Request-ID + version 双重幂等
        - 错误处理: 版本号冲突返回 1005，Python 端放弃本次归档
        - 规则条款: C-3.4, C-4.9, C-6.5, C-6.6

        Args:
            session_id: 会话 ID
            user_id: 用户 ID
            summary: 摘要文本
            version: 摘要版本号
            token_count: 摘要 token 数
            trigger_reason: 触发原因 (session_end, window_threshold, user_request)
            request_id: 幂等键（X-Request-ID），不传则自动生成
            trace_id: 链路追踪 ID（X-Trace-ID），不传则自动生成

        Returns:
            Java 端响应 dict，包含 {archived: bool, version: int}
        """
        import uuid as _uuid
        from datetime import datetime, timezone

        if request_id is None:
            request_id = f"req_{_uuid.uuid4().hex[:16]}"
        if trace_id is None:
            trace_id = f"trace_{_uuid.uuid4().hex[:16]}"

        payload = {
            "session_id": session_id,
            "user_id": user_id,
            "summary": summary,
            "version": version,
            "token_count": token_count,
            "trigger_reason": trigger_reason,
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }

        try:
            client = await self._get_client()
            resp = await client.post(
                "/api/v1/callback/session-summary",
                json=payload,
                headers={
                    "X-Request-ID": request_id,
                    "X-Trace-ID": trace_id,
                },
                timeout=10.0,
            )
            resp.raise_for_status()
            return dict(resp.json())
        except Exception as e:
            logger.warning(f"Failed to send session summary callback: {e}")
            return {"status": "failed", "error": str(e)}

    async def export_memory(
        self,
        user_id: str,
        request_id: str | None = None,
        trace_id: str | None = None,
    ) -> dict[str, Any]:
        """S5.10: 记忆导出接口（FR-SM-004 / spec 7.10）。

        Calls GET /api/v1/memory/export?user_id={user_id} to export all memory
        data (memory_chunks, session_summaries, strategy_records, user_profile)
        for offline verification and data portability (72-hour SLA per spec 9.5).

        Args:
            user_id: 用户 ID
            request_id: 幂等键（X-Request-ID），不传则自动生成
            trace_id: 链路追踪 ID（X-Trace-ID），不传则自动生成

        Returns:
            Java 端响应 dict，包含 export_time/user_id/memory_chunks/
            session_summaries/strategy_records/user_profile
        """
        import uuid as _uuid

        if request_id is None:
            request_id = f"req_{_uuid.uuid4().hex[:16]}"
        if trace_id is None:
            trace_id = f"trace_{_uuid.uuid4().hex[:16]}"

        try:
            client = await self._get_client()
            resp = await client.get(
                "/api/v1/memory/export",
                params={"user_id": user_id},
                headers={
                    "X-Request-ID": request_id,
                    "X-Trace-ID": trace_id,
                },
                timeout=30.0,
            )
            resp.raise_for_status()
            return dict(resp.json())
        except Exception as e:
            logger.warning(f"Failed to export memory for user={user_id}: {e}")
            return {"status": "failed", "error": str(e)}

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
