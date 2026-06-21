"""L3 Retrieval Layer: WebSearcher — 联网搜索能力。

通过 MCP Client 调用外部搜索 API（Tavily/Bing/SerpAPI），支持：
- 多搜索源并行搜索
- 结果排序（相关性 + 来源偏好）
- 搜索结果缓存（L0 + L1）
- API 不可用时优雅降级
"""
import asyncio
import hashlib
import json
import logging
import time
from typing import Any

from app.infrastructure.l0_cache import L0Cache
from app.infrastructure.redis_client import redis_client
from app.models.search_result import SearchResult

logger = logging.getLogger(__name__)


class WebSearcher:
    """联网搜索器 — 通过 MCP Client 调用搜索 API。"""

    SEARCH_CACHE_TTL: int = 1800  # 30 minutes
    SEARCH_TIMEOUT: float = 10.0

    def __init__(self) -> None:
        self._l0_cache: L0Cache = L0Cache(max_size=256)

    def _cache_key(self, query: str) -> str:
        qhash = hashlib.md5(query.encode()).hexdigest()[:12]
        return f"search:{qhash}"

    def _redis_key(self, query: str, user_id: str = "") -> str:
        """S3.9/FIX-KEY-2: 搜索缓存键加入 user_id 隔离（Redis-Key规范文档 §3.6）。

        旧格式: shardflow:search:cache:{hash}（无 user_id，跨用户缓存污染）
        新格式: shardflow:{user_id}:search:{hash}（用户隔离）
        """
        qhash = hashlib.md5(query.encode()).hexdigest()[:12]
        # S3.9: user_id 为空时使用 "anonymous" 兜底，避免跨用户污染
        uid = user_id or "anonymous"
        return f"shardflow:{uid}:search:{qhash}"

    async def search(
        self,
        query: str,
        source_preference: dict[str, float] | None = None,
        user_id: str = "",
    ) -> list[SearchResult]:
        """执行联网搜索。

        Args:
            query: 搜索关键词
            source_preference: 来源偏好权重（可选）
            user_id: 用户 ID（S3.9: 用于搜索缓存用户隔离）

        Returns:
            搜索结果列表（按相关性排序）
        """
        # 检查缓存
        cached = await self._get_cache(query, user_id)
        if cached is not None:
            return cached

        # 通过 MCP Client 调用搜索
        results: list[SearchResult] = []
        try:
            from app.layers.agent_core.mcp_client import mcp_client
            mcp_result = await mcp_client.call_tool("web_search", {"query": query})
            if mcp_result.success and mcp_result.data:
                results = self._parse_mcp_results(mcp_result.data)
        except Exception as e:
            logger.warning(f"MCP web_search failed: {e}")

        # 并行多源搜索（如果 MCP 支持多源）
        if not results:
            results = await self._multi_source_fallback(query)

        # 排序（基于来源偏好）
        if source_preference:
            results = self._rank_by_preference(results, source_preference)
        else:
            results = sorted(results, key=lambda r: r.relevance_score, reverse=True)

        # 缓存结果
        await self._set_cache(query, results, user_id)

        return results

    async def _get_cache(self, query: str, user_id: str = "") -> list[SearchResult] | None:
        cache_key = self._cache_key(query)
        cached = self._l0_cache.get(cache_key)
        if cached is not None:
            return cached if isinstance(cached, list) else None

        try:
            r = await redis_client.get_redis()
            raw = await r.get(self._redis_key(query, user_id))
            if raw:
                data = json.loads(raw)
                results = [SearchResult(**item) for item in data]
                self._l0_cache.set(cache_key, results)
                return results
        except Exception:
            pass
        return None

    async def _set_cache(self, query: str, results: list[SearchResult], user_id: str = "") -> None:
        cache_key = self._cache_key(query)
        self._l0_cache.set(cache_key, results)
        try:
            r = await redis_client.get_redis()
            await r.set(
                self._redis_key(query, user_id),
                json.dumps([r.model_dump() for r in results]),
                ex=self.SEARCH_CACHE_TTL,
            )
        except Exception:
            pass

    async def _multi_source_fallback(self, query: str) -> list[SearchResult]:
        """多源搜索 fallback（当 MCP 不可用时）。"""
        results: list[SearchResult] = []
        # 尝试通过 HTTP 直接调用 Tavily API
        try:
            import httpx
            from app.config import settings
            tavily_key = getattr(settings, 'tavily_api_key', '') or settings.llm_api_key
            if tavily_key:
                async with httpx.AsyncClient(timeout=self.SEARCH_TIMEOUT) as client:
                    resp = await client.post(
                        "https://api.tavily.com/search",
                        json={
                            "api_key": tavily_key,
                            "query": query,
                            "search_depth": "basic",
                            "max_results": 5,
                        },
                    )
                    if resp.status_code == 200:
                        data = resp.json()
                        for item in data.get("results", []):
                            results.append(SearchResult(
                                source="web_search",
                                title=str(item.get("title", "")),
                                snippet=str(item.get("content", ""))[:500],
                                url=str(item.get("url", "")),
                                relevance_score=float(item.get("score", 0.7)),
                            ))
        except Exception as e:
            logger.debug(f"Tavily fallback failed: {e}")

        return results

    def _parse_mcp_results(self, data: dict[str, Any]) -> list[SearchResult]:
        """从 MCP 返回结果中解析搜索条目。"""
        results: list[SearchResult] = []
        content = data.get("content", data)
        if isinstance(content, str):
            try:
                content = json.loads(content)
            except json.JSONDecodeError:
                return results

        items = content if isinstance(content, list) else content.get("results", [])
        for item in items:
            if isinstance(item, dict):
                results.append(SearchResult(
                    source=item.get("source", "web_search"),
                    title=str(item.get("title", "")),
                    snippet=str(item.get("snippet", item.get("content", "")))[:500],
                    url=str(item.get("url", item.get("link", ""))),
                    relevance_score=float(item.get("score", item.get("relevance_score", 0.6))),
                ))
        return results

    def _rank_by_preference(self, results: list[SearchResult],
                            preferences: dict[str, float]) -> list[SearchResult]:
        """基于来源偏好重排序。"""
        for r in results:
            pref_weight = preferences.get(r.source, 0.5)
            r.relevance_score = r.relevance_score * 0.7 + pref_weight * 0.3
        return sorted(results, key=lambda r: r.relevance_score, reverse=True)

    async def invalidate_cache(self, query: str) -> None:
        self._l0_cache.invalidate(self._cache_key(query))
        try:
            r = await redis_client.get_redis()
            await r.delete(self._redis_key(query))
        except Exception:
            pass


web_searcher = WebSearcher()
