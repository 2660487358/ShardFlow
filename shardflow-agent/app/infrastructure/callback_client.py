from typing import Any

import httpx

from app.config import settings


class CallbackClient:
    def __init__(self) -> None:
        self._base_url = settings.java_base_url
        self._client: httpx.AsyncClient | None = None

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

    async def save_shard(self, shard: dict[str, Any]) -> dict[str, Any]:
        client = await self._get_client()
        resp = await client.post("/api/v1/callback/shards", json=shard)
        resp.raise_for_status()
        return dict(resp.json())

    async def save_strategy(self, strategy: dict[str, Any]) -> dict[str, Any]:
        client = await self._get_client()
        resp = await client.post("/api/v1/callback/strategies", json=strategy)
        resp.raise_for_status()
        return dict(resp.json())

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

    async def get_shard(self, task_id: str) -> dict[str, Any] | None:
        client = await self._get_client()
        resp = await client.get(f"/api/v1/shards/{task_id}")
        if resp.status_code == 404:
            return None
        resp.raise_for_status()
        return dict(resp.json())

    async def search_strategies(self, task_type: str, query: str,
                                embedding: list[float] | None = None,
                                limit: int = 5) -> list[dict[str, Any]]:
        """Proxy semantic search through Java kb-strategy pgvector API."""
        client = await self._get_client()
        body: dict[str, Any] = {
            "task_type": task_type,
            "query": query,
            "limit": limit,
        }
        if embedding:
            body["embedding"] = embedding
        resp = await client.post("/api/v1/strategies/search", json=body)
        resp.raise_for_status()
        data = resp.json()
        return data.get("results", data) if isinstance(data, dict) else data

    async def close(self) -> None:
        if self._client:
            await self._client.aclose()
            self._client = None

    async def update_profile(self, user_id: str, updates: dict[str, Any]) -> dict[str, Any]:
        """Callback to Java kb-callback to update user profile.

        POST /api/v1/callback/profile
        Idempotency key: user_id
        """
        client = await self._get_client()
        resp = await client.post(
            "/api/v1/callback/profile",
            json={"user_id": user_id, "updates": updates},
        )
        resp.raise_for_status()
        return dict(resp.json())


callback_client = CallbackClient()
