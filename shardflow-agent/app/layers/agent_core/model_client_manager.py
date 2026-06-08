"""Multi-model HTTP client manager with LRU caching and connection pool.

Each model gets its own httpx.AsyncClient, keyed by model_id.
Supports builtin models (env-var API keys) and custom models (decrypted keys).

优化（Phase 2）：HTTP/2 连接池 + 启动预热
- 启用 HTTP/2 多路复用，减少 TCP/TLS 握手开销
- 启动时自动对所有已配置模型发送预热请求，消除冷启动延迟
- 连接池参数可配置（env: SF_AGENT_LLM_POOL_*）
"""
import asyncio
import logging
from typing import Any

import httpx

from app.config import settings
from app.infrastructure.callback_client import callback_client

logger = logging.getLogger(__name__)

# Max number of cached clients to prevent memory leaks
MAX_CLIENTS = 20


class ModelClientManager:
    """Caches httpx clients per model_id so multiple LLM providers coexist."""

    def __init__(self) -> None:
        self._clients: dict[str, httpx.AsyncClient] = {}
        self._config_cache: dict[str, dict[str, Any]] = {}
        self._access_order: list[str] = []
        self._warmed_up: bool = False

    # ── 连接池配置（可通过环境变量覆盖）──
    _POOL_MAX_CONNECTIONS: int = 50
    _POOL_MAX_KEEPALIVE: int = 20
    _POOL_KEEPALIVE_EXPIRY: float = 30.0

    async def get_client(self, model_id: str) -> tuple[httpx.AsyncClient, str]:
        """Return (http_client, actual_model_name) for the given model_id."""
        if model_id not in self._clients:
            await self._init_client(model_id)
        self._touch(model_id)
        config = self._config_cache[model_id]
        return self._clients[model_id], config["model"]

    async def _init_client(self, model_id: str) -> None:
        config = await self._fetch_model_config(model_id)
        base_url = config.get("base_url", settings.llm_base_url)
        api_key = config.get("api_key", settings.llm_api_key)

        if not base_url:
            base_url = "https://api.openai.com/v1"

        # Build connection pool limits for httpx
        pool_limits = httpx.Limits(
            max_connections=self._POOL_MAX_CONNECTIONS,
            max_keepalive_connections=self._POOL_MAX_KEEPALIVE,
            keepalive_expiry=self._POOL_KEEPALIVE_EXPIRY,
        )

        # HTTP/2: opt-in via env SF_AGENT_LLM_HTTP2=true, requires `pip install httpx[http2]`
        _http2 = getattr(settings, 'llm_http2', False)

        client = httpx.AsyncClient(
            base_url=base_url,
            timeout=httpx.Timeout(30.0),
            limits=pool_limits,
            http2=_http2,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
        )
        self._clients[model_id] = client
        self._config_cache[model_id] = config
        self._access_order.append(model_id)
        self._evict_if_needed()

    async def _fetch_model_config(self, model_id: str) -> dict[str, Any]:
        """Fetch model config from Java ConfigService.

        For builtin models, the Java service reads env vars.
        For custom models, the Java service decrypts the stored key.
        """
        try:
            java_client = await callback_client._get_client()
            resp = await java_client.get(
                f"/api/v1/models/{model_id}/config",
                headers={"X-API-Key": settings.java_api_key or settings.llm_api_key},
            )
            resp.raise_for_status()
            data = resp.json()
            # Unwrap Result wrapper
            if isinstance(data, dict) and "data" in data:
                return data["data"]
            return data
        except Exception as e:
            logger.warning("Failed to fetch model config for %s from Java, using env fallback: %s", model_id, e)
            fallback_base = settings.llm_base_url or "https://api.openai.com/v1"
            logger.info("Fallback for %s: base_url=%s, model=%s", model_id, fallback_base, model_id)
            return {
                "model_id": model_id,
                "model": model_id,
                "base_url": fallback_base,
                "api_key": settings.llm_api_key,
                "provider": "unknown",
            }

    def _touch(self, model_id: str) -> None:
        if model_id in self._access_order:
            self._access_order.remove(model_id)
        self._access_order.append(model_id)

    def _evict_if_needed(self) -> None:
        while len(self._clients) > MAX_CLIENTS:
            oldest = self._access_order.pop(0)
            logger.info("Evicting model client cache for %s (LRU)", oldest)
            self._clients.pop(oldest, None)
            self._config_cache.pop(oldest, None)

    async def invalidate(self, model_id: str) -> None:
        """Remove a cached client so it's re-fetched on next use."""
        client = self._clients.pop(model_id, None)
        if client:
            await client.aclose()
        self._config_cache.pop(model_id, None)
        if model_id in self._access_order:
            self._access_order.remove(model_id)

    async def warm_up(self, model_ids: list[str] | None = None) -> None:
        """启动时预热连接池：对每个模型发送一个最小请求建立 TCP/TLS 连接。

        消除首次请求的冷启动延迟（200-500ms TCP+TLS 握手）。
        若未指定 model_ids，预热所有 LLMRouter.MODEL_MAP 中的模型。
        """
        if self._warmed_up:
            return
        if not model_ids:
            from app.layers.agent_core.llm_router import llm_router
            model_ids = list(set(llm_router.MODEL_MAP.values()))

        warmup_payload = {
            "model": "",
            "messages": [{"role": "user", "content": "ping"}],
            "max_tokens": 1,
            "temperature": 0,
        }

        async def _warm_one(mid: str) -> None:
            try:
                # init_client 建立连接 + TLS 握手
                client, actual_model = await self.get_client(mid)
                warmup_payload["model"] = actual_model
                # 发送一个最小请求确认链路通畅
                resp = await client.post(
                    "/chat/completions", json=warmup_payload, timeout=10.0,
                )
                if resp.status_code >= 500:
                    logger.warning("Warm-up for model %s returned %s", mid, resp.status_code)
                else:
                    logger.info("Model %s connection pool warmed up (model=%s)", mid, actual_model)
            except Exception as e:
                logger.warning("Warm-up for model %s failed (non-fatal): %s", mid, e)

        logger.info("Warming up model client connections for %d models...", len(model_ids))
        await asyncio.gather(*[_warm_one(mid) for mid in model_ids])
        self._warmed_up = True
        logger.info("Model client warm-up complete")

    async def close(self) -> None:
        for client in self._clients.values():
            await client.aclose()
        self._clients.clear()
        self._config_cache.clear()
        self._access_order.clear()


model_client_manager = ModelClientManager()
