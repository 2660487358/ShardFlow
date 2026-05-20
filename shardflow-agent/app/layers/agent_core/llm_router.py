import asyncio
from enum import Enum
from typing import Any

import httpx

from app.config import settings


class TaskComplexity(str, Enum):
    SIMPLE = "simple"
    COMPLEX = "complex"


class LLMRouter:
    """Routes LLM calls to appropriate models with retry and fallback logic."""

    MODEL_MAP: dict[str, str] = {
        "complex": "gpt-4o",
        "simple": "gpt-4o-mini",
        "fallback": "gpt-4o-mini",
    }

    TASK_MODEL: dict[str, str] = {
        "intent_recognition": "simple",
        "think": "complex",
        "summarize": "simple",
        "shard_extract": "complex",
        "observe": "simple",
    }

    def __init__(self) -> None:
        self._client: httpx.AsyncClient | None = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                base_url=settings.llm_base_url,
                timeout=httpx.Timeout(30.0),
                headers={
                    "Authorization": f"Bearer {settings.llm_api_key}",
                    "Content-Type": "application/json",
                },
            )
        return self._client

    def select_model(self, task_type: str) -> str:
        complexity = self.TASK_MODEL.get(task_type, "simple")
        return self.MODEL_MAP[complexity]

    def fallback_model(self) -> str:
        return self.MODEL_MAP["fallback"]

    async def call_llm(self, prompt: str, model: str, system_prompt: str = "") -> dict[str, Any]:
        client = await self._get_client()
        messages: list[dict[str, Any]] = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        resp = await client.post("/chat/completions", json={
            "model": model,
            "messages": messages,
            "temperature": 0.3,
            "max_tokens": 4096,
        })
        resp.raise_for_status()
        return dict(resp.json())

    async def call_with_retry(
        self, prompt: str, model: str, system_prompt: str = "", retries: int = 2
    ) -> dict[str, Any]:
        last_error: Exception | None = None
        current_model = model

        for attempt in range(retries + 1):
            try:
                return await self.call_llm(prompt, current_model, system_prompt)
            except httpx.TimeoutException as e:
                last_error = e
                if attempt < retries:
                    await asyncio.sleep(1.0 * (2 ** attempt))
            except httpx.HTTPStatusError as e:
                if e.response.status_code == 429:
                    last_error = e
                    retry_after = int(e.response.headers.get("Retry-After", "2"))
                    await asyncio.sleep(float(retry_after))
                elif e.response.status_code >= 500:
                    last_error = e
                    if attempt < retries:
                        await asyncio.sleep(1.0 * (2 ** attempt))
                else:
                    raise
            except Exception as e:
                last_error = e
                if attempt < retries:
                    await asyncio.sleep(1.0 * (2 ** attempt))

            if attempt == retries - 1 and current_model != self.fallback_model():
                current_model = self.fallback_model()

        raise last_error or RuntimeError("LLM call failed after retries")

    async def extract_content(self, response: dict[str, Any]) -> str:
        choices = response.get("choices", [])
        if not choices:
            return ""
        content: str = choices[0].get("message", {}).get("content", "")
        return content

    async def close(self) -> None:
        if self._client:
            await self._client.aclose()
            self._client = None


llm_router = LLMRouter()
