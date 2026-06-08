import asyncio
import json
import logging
from enum import Enum
from typing import Any, AsyncIterator

import httpx

from app.config import settings

logger = logging.getLogger(__name__)


class TaskComplexity(str, Enum):
    SIMPLE = "simple"
    COMPLEX = "complex"


class LLMRouter:
    """Routes LLM calls to appropriate models with multi-provider support.

    Uses ModelClientManager to dynamically resolve model_id → (client, actual_model_name).
    Supports builtin models (env-var keys) and custom models (decrypted keys from config service).
    """

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
        self._fallback_client: httpx.AsyncClient | None = None

    async def _get_fallback_client(self) -> httpx.AsyncClient:
        if self._fallback_client is None:
            base_url = settings.llm_base_url or "https://api.openai.com/v1"
            self._fallback_client = httpx.AsyncClient(
                base_url=base_url,
                timeout=httpx.Timeout(30.0),
                headers={
                    "Authorization": f"Bearer {settings.llm_api_key}",
                    "Content-Type": "application/json",
                },
            )
        return self._fallback_client

    def select_model(self, task_type: str) -> str:
        complexity = self.TASK_MODEL.get(task_type, "simple")
        return self.MODEL_MAP[complexity]

    def fallback_model(self) -> str:
        return self.MODEL_MAP["fallback"]

    def _build_messages(self, prompt: str, system_prompt: str = "") -> list[dict[str, Any]]:
        messages: list[dict[str, Any]] = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})
        return messages

    async def call_llm(
        self, prompt: str, model_id: str, system_prompt: str = ""
    ) -> dict[str, Any]:
        """Call LLM with dynamic model_id routing (non-streaming)."""
        from app.layers.agent_core.model_client_manager import model_client_manager

        messages = self._build_messages(prompt, system_prompt)
        payload: dict[str, Any] = {
            "model": model_id,
            "messages": messages,
            "temperature": 0.3,
            "max_tokens": 4096,
        }

        try:
            client, actual_model = await model_client_manager.get_client(model_id)
            payload["model"] = actual_model
            logger.info(
                "LLM call: model_id=%s actual_model=%s base_url=%s",
                model_id, actual_model, str(client.base_url),
            )
            resp = await client.post("/chat/completions", json=payload)
            if resp.status_code >= 400:
                logger.error(
                    "LLM %s returned %s: %s",
                    model_id, resp.status_code, resp.text[:500],
                )
            resp.raise_for_status()
            return dict(resp.json())
        except Exception:
            # Fallback to global client
            payload["model"] = self.fallback_model()
            client = await self._get_fallback_client()
            resp = await client.post("/chat/completions", json=payload)
            if resp.status_code >= 400:
                logger.error(
                    "Fallback LLM returned %s: %s",
                    resp.status_code, resp.text[:500],
                )
            resp.raise_for_status()
            return dict(resp.json())

    async def call_llm_stream(
        self, prompt: str, model_id: str, system_prompt: str = "",
    ) -> AsyncIterator[str]:
        """Call LLM with streaming, yielding content tokens as they arrive.

        Returns an async generator that yields each content delta as a string.
        The caller must consume the entire generator to complete the request.
        """
        from app.layers.agent_core.model_client_manager import model_client_manager

        messages = self._build_messages(prompt, system_prompt)
        payload: dict[str, Any] = {
            "model": model_id,
            "messages": messages,
            "temperature": 0.3,
            "max_tokens": 4096,
            "stream": True,
        }

        client, actual_model = await model_client_manager.get_client(model_id)
        payload["model"] = actual_model
        logger.info(
            "LLM stream: model_id=%s actual_model=%s base_url=%s",
            model_id, actual_model, str(client.base_url),
        )

        async with client.stream("POST", "/chat/completions", json=payload) as resp:
            if resp.status_code >= 400:
                error_body = await resp.aread()
                logger.error(
                    "LLM stream %s returned %s: %s",
                    model_id, resp.status_code, error_body[:500],
                )
                resp.raise_for_status()
            async for line in resp.aiter_lines():
                if line.startswith("data: "):
                    data_str = line[6:]
                    if data_str.strip() == "[DONE]":
                        return
                    try:
                        obj = json.loads(data_str)
                        delta = obj.get("choices", [{}])[0].get("delta", {})
                        content = delta.get("content", "")
                        if content:
                            yield content
                    except json.JSONDecodeError:
                        continue

    async def call_stream_with_retry(
        self, prompt: str, model_id: str, system_prompt: str = "", retries: int = 1
    ) -> AsyncIterator[str]:
        """Streaming LLM call with fallback on error."""
        last_error: Exception | None = None
        current_model = model_id

        for attempt in range(retries + 1):
            try:
                async for token in self.call_llm_stream(prompt, current_model, system_prompt):
                    yield token
                return  # success
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

        raise last_error or RuntimeError("LLM stream call failed after retries")

    async def call_with_retry(
        self, prompt: str, model_id: str, system_prompt: str = "", retries: int = 2
    ) -> dict[str, Any]:
        last_error: Exception | None = None
        current_model = model_id

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
        from app.layers.agent_core.model_client_manager import model_client_manager
        await model_client_manager.close()
        if self._fallback_client:
            await self._fallback_client.aclose()
            self._fallback_client = None


llm_router = LLMRouter()
