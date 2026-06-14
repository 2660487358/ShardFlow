"""JavaAPIAdapter — HTTP adapter for L2 tier persistence through Java services.

Implements real CRUD operations against Java peripheral service APIs:
- Memory chunks: /api/v1/memory/*
- Session summaries: /api/v1/session-summary/*
- Strategy records: /api/v1/strategy/*
- User profiles: /api/v1/profile/*
"""
import logging
from datetime import datetime, timezone
from typing import Any

import httpx

from app.config import settings
from app.models.memory import MemoryRecord, MemoryQuery, MemoryType

logger = logging.getLogger(__name__)


class JavaAPIAdapter:
    """Java peripheral service adapter for L2 tier (< 50ms target).

    Routes memory operations to the appropriate Java API endpoints based on MemoryType.
    Maintains its own httpx.AsyncClient instance, independent of CallbackClient.
    """

    def __init__(self) -> None:
        self._client: httpx.AsyncClient | None = None
        self._base_url = settings.java_base_url

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

    async def close(self) -> None:
        if self._client:
            await self._client.aclose()
            self._client = None

    # ── Read ──

    async def read(self, user_id: str, memory_type: MemoryType, key: str) -> MemoryRecord | None:
        """Read a memory record from Java service. Returns None on any failure."""
        try:
            client = await self._get_client()
            headers = {"X-User-Id": user_id}

            if memory_type == MemoryType.SESSION_SUMMARY:
                resp = await client.get(
                    "/api/v1/session-summary",
                    params={"user_id": user_id, "task_id": key},
                    headers=headers,
                )
            elif memory_type == MemoryType.SEMANTIC and key == "__profile__":
                resp = await client.get(
                    f"/api/v1/profile/{user_id}",
                    headers=headers,
                )
            elif memory_type in (MemoryType.SEMANTIC, MemoryType.EPISODIC):
                resp = await client.get(
                    f"/api/v1/memory/{key}",
                    headers=headers,
                )
            elif memory_type == MemoryType.SHORT_TERM:
                return None
            else:
                return None

            if resp.status_code == 404:
                return None
            resp.raise_for_status()

            data = resp.json()
            payload = data.get("data", data)
            return self._response_to_record(memory_type, key, user_id, payload)

        except Exception as e:
            logger.warning("L2 read failed for %s/%s: %s", memory_type.value, key, e)
            return None

    # ── Write ──

    async def write(self, user_id: str, memory_type: MemoryType, key: str,
                    data: dict[str, Any], ttl_seconds: int = 0) -> MemoryRecord | None:
        """Write a memory record to Java service.

        Returns MemoryRecord on success, None on failure.
        SHORT_TERM is not persisted to L2 — returns None (no-op).
        """
        try:
            client = await self._get_client()
            headers = {"X-User-Id": user_id}

            if memory_type == MemoryType.SESSION_SUMMARY:
                body = {"user_id": user_id, "task_id": key, **data}
                resp = await client.post(
                    "/api/v1/session-summary",
                    json=body,
                    headers=headers,
                )
            elif memory_type == MemoryType.SEMANTIC and key == "__profile__":
                body = {"user_id": user_id, **data}
                resp = await client.put(
                    f"/api/v1/profile/{user_id}",
                    json=body,
                    headers=headers,
                )
            elif memory_type in (MemoryType.SEMANTIC, MemoryType.EPISODIC):
                body = {
                    "user_id": user_id,
                    "memory_type": memory_type.value,
                    "content": {"text": data.get("text", ""), "structured": data.get("structured", {})},
                    "confidence": data.get("confidence", 1.0),
                    "source": data.get("source", "conversation"),
                    "session_id": data.get("session_id", ""),
                }
                resp = await client.post(
                    "/api/v1/memory",
                    json=body,
                    headers=headers,
                )
            elif memory_type == MemoryType.SHORT_TERM:
                return None
            else:
                return None

            resp.raise_for_status()

            now = datetime.now(timezone.utc)
            return MemoryRecord(
                key=key, user_id=user_id, memory_type=memory_type,
                data=data, updated_at=now,
            )

        except Exception as e:
            logger.warning("L2 write failed for %s/%s: %s", memory_type.value, key, e)
            return None

    # ── Delete ──

    async def delete(self, user_id: str, memory_type: MemoryType, key: str) -> bool:
        """Delete a memory record from Java service (logical delete)."""
        try:
            client = await self._get_client()
            headers = {"X-User-Id": user_id}

            if memory_type in (MemoryType.SEMANTIC, MemoryType.EPISODIC):
                if memory_type == MemoryType.SEMANTIC and key == "__profile__":
                    resp = await client.delete(f"/api/v1/profile/{user_id}", headers=headers)
                else:
                    resp = await client.delete(f"/api/v1/memory/{key}", headers=headers)
                return resp.status_code in (200, 204)
            elif memory_type == MemoryType.SESSION_SUMMARY:
                resp = await client.delete(
                    f"/api/v1/session-summary/{key}", headers=headers,
                )
                return resp.status_code in (200, 204)
            else:
                return False

        except Exception as e:
            logger.warning("L2 delete failed for %s/%s: %s", memory_type.value, key, e)
            return False

    # ── Search ──

    async def search(self, user_id: str, memory_type: MemoryType,
                     query: MemoryQuery) -> list[MemoryRecord]:
        """Search memory records via Java service."""
        try:
            client = await self._get_client()
            headers = {"X-User-Id": user_id}

            if memory_type in (MemoryType.SEMANTIC, MemoryType.EPISODIC):
                body = {
                    "user_id": user_id,
                    "query": query.key_prefix or "",
                    "search_type": "structured",
                    "top_k": query.limit,
                    "filters": {
                        "memory_type": [memory_type.value],
                        "min_confidence": 0.5,
                    },
                }
                resp = await client.post(
                    "/api/v1/memory/search",
                    json=body,
                    headers=headers,
                )
                resp.raise_for_status()
                data = resp.json()
                results = data.get("data", {}).get("results", data.get("results", []))
                return [
                    MemoryRecord(
                        key=r.get("memory_id", ""),
                        user_id=user_id,
                        memory_type=memory_type,
                        data={"text": r.get("content", ""), "similarity_score": r.get("similarity_score", 0)},
                        tags=[r.get("category", "")],
                    )
                    for r in results
                ]
            elif memory_type == MemoryType.SESSION_SUMMARY:
                return []

            return []

        except Exception as e:
            logger.warning("L2 search failed for %s: %s", memory_type.value, e)
            return []

    # ── Exists ──

    async def exists(self, user_id: str, memory_type: MemoryType, key: str) -> bool:
        record = await self.read(user_id, memory_type, key)
        return record is not None

    # ── Helpers ──

    def _response_to_record(self, memory_type: MemoryType, key: str,
                            user_id: str, payload: dict) -> MemoryRecord:
        """Convert a Java API response payload to a MemoryRecord."""
        return MemoryRecord(
            key=payload.get("memory_id", payload.get("summary_id", key)),
            user_id=user_id,
            memory_type=memory_type,
            data=payload,
            created_at=datetime.fromisoformat(payload["created_at"]) if payload.get("created_at") else datetime.now(timezone.utc),
            updated_at=datetime.fromisoformat(payload["updated_at"]) if payload.get("updated_at") else datetime.now(timezone.utc),
            version=payload.get("version", 1),
        )
