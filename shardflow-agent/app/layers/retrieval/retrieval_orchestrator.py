"""L3 Retrieval Layer: multi-source search with real API adapters, rate limiting, and degradation.

Three adapters:
- OfficialDocAdapter: ReadTheDocs / generic documentation search
- StackOverflowAdapter: StackExchange API v2.3 (answers, questions, search)
- GitHubAdapter: GitHub REST API v3 (code search, repo search)

Each adapter supports:
- Real API call with authentication
- Rate limiting via token bucket
- Graceful degradation to Mock source on failure/timeout
"""
import asyncio
import logging
import time
from typing import Any

import httpx

from app.config import settings
from app.layers.tool.result_parser import result_parser as _result_parser
from app.models.search_result import SearchResult

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Token Bucket rate limiter
# ---------------------------------------------------------------------------

class TokenBucket:
    """Simple async token bucket for rate limiting."""

    def __init__(self, rate: float, burst: int) -> None:
        self._rate = rate          # tokens per second
        self._burst = burst        # max tokens
        self._tokens = float(burst)
        self._last_refill = time.monotonic()
        self._lock = asyncio.Lock()

    async def acquire(self) -> bool:
        async with self._lock:
            now = time.monotonic()
            elapsed = now - self._last_refill
            self._tokens = min(self._burst, self._tokens + elapsed * self._rate)
            self._last_refill = now
            if self._tokens >= 1.0:
                self._tokens -= 1.0
                return True
            return False


# ---------------------------------------------------------------------------
# Base adapter with degradation
# ---------------------------------------------------------------------------

class SearchAdapter:
    """Base class for search adapters with fallback-to-mock support."""

    def __init__(self, source_name: str, rate: float = 10.0, burst: int = 5):
        self.source_name = source_name
        self._bucket = TokenBucket(rate, burst)

    async def search(self, query: str) -> list[SearchResult]:
        raise NotImplementedError

    def _mock_search(self, query: str) -> list[SearchResult]:
        """Fallback mock when real API is unavailable."""
        return [SearchResult(
            source=self.source_name,
            title=f"{self.source_name}: {query[:80]}",
            snippet=f"Mock result for: {query[:200]}",
            url=f"https://example.com/search?q={query[:50]}",
            relevance_score=0.5,
        )]


# ---------------------------------------------------------------------------
# OfficialDoc Adapter — ReadTheDocs / generic docs search
# ---------------------------------------------------------------------------

class OfficialDocAdapter(SearchAdapter):
    """Search official documentation via configurable docs base URL."""

    DOCS_API_BASE = "https://api.readthedocs.org/api/v3"

    def __init__(self) -> None:
        super().__init__("official_doc", rate=5.0, burst=3)

    async def search(self, query: str) -> list[SearchResult]:
        if not await self._bucket.acquire():
            logger.warning("OfficialDoc rate limit hit, using mock")
            return self._mock_search(query) if settings.retrieval_fallback_to_mock else []

        try:
            async with httpx.AsyncClient(timeout=settings.retrieval_timeout) as client:
                resp = await client.get(
                    f"{self.DOCS_API_BASE}/search/",
                    params={"q": query, "project": "feature", "version": "latest"},
                )
                resp.raise_for_status()
                data = resp.json()
                results: list[SearchResult] = []
                for item in data.get("results", [])[:5]:
                    results.append(SearchResult(
                        source="official_doc",
                        title=str(item.get("title", item.get("name", ""))),
                        snippet=str(item.get("highlight", {}).get("content", [item.get("description", "")]))[:500],
                        url=str(item.get("links", {}).get("_self", item.get("url", ""))),
                        relevance_score=float(item.get("score", 0.7)),
                    ))
                return results or self._mock_search(query)
        except Exception as e:
            logger.warning(f"OfficialDoc API failed: {e}")
            return self._mock_search(query) if settings.retrieval_fallback_to_mock else []


# ---------------------------------------------------------------------------
# StackOverflow Adapter — StackExchange API v2.3
# ---------------------------------------------------------------------------

class StackOverflowAdapter(SearchAdapter):
    """Search StackOverflow via StackExchange API."""

    SE_API_BASE = "https://api.stackexchange.com/2.3"

    def __init__(self) -> None:
        super().__init__("stackoverflow", rate=30.0, burst=10)

    async def search(self, query: str) -> list[SearchResult]:
        if not await self._bucket.acquire():
            logger.warning("StackOverflow rate limit hit, using mock")
            return self._mock_search(query) if settings.retrieval_fallback_to_mock else []

        try:
            async with httpx.AsyncClient(timeout=settings.retrieval_timeout) as client:
                params: dict[str, Any] = {
                    "order": "desc",
                    "sort": "relevance",
                    "q": query,
                    "site": "stackoverflow",
                    "pagesize": 5,
                    "filter": "withbody",
                }
                if settings.stackexchange_api_key:
                    params["key"] = settings.stackexchange_api_key

                resp = await client.get(f"{self.SE_API_BASE}/search/advanced", params=params)
                resp.raise_for_status()
                data = resp.json()
                results: list[SearchResult] = []
                for item in data.get("items", [])[:5]:
                    title = str(item.get("title", ""))
                    body = str(item.get("body", ""))
                    # Strip HTML tags for snippet
                    snippet = _strip_html(body)[:500]
                    results.append(SearchResult(
                        source="stackoverflow",
                        title=title,
                        snippet=snippet,
                        url=str(item.get("link", "")),
                        relevance_score=float(item.get("score", 0.6)),
                        metadata={
                            "answer_count": item.get("answer_count", 0),
                            "is_answered": item.get("is_answered", False),
                            "tags": item.get("tags", []),
                        },
                    ))
                return results or self._mock_search(query)
        except Exception as e:
            logger.warning(f"StackOverflow API failed: {e}")
            return self._mock_search(query) if settings.retrieval_fallback_to_mock else []


# ---------------------------------------------------------------------------
# GitHub Adapter — GitHub REST API v3 (code search)
# ---------------------------------------------------------------------------

class GitHubAdapter(SearchAdapter):
    """Search code and repositories via GitHub REST API."""

    GH_API_BASE = "https://api.github.com"

    def __init__(self) -> None:
        super().__init__("github", rate=10.0, burst=5)

    async def search(self, query: str) -> list[SearchResult]:
        if not await self._bucket.acquire():
            logger.warning("GitHub rate limit hit, using mock")
            return self._mock_search(query) if settings.retrieval_fallback_to_mock else []

        try:
            async with httpx.AsyncClient(timeout=settings.retrieval_timeout) as client:
                headers: dict[str, str] = {"Accept": "application/vnd.github.v3+json"}
                if settings.github_token:
                    headers["Authorization"] = f"token {settings.github_token}"

                # Search code only (not repos/issues) for precision
                resp = await client.get(
                    f"{self.GH_API_BASE}/search/code",
                    params={"q": query, "per_page": 5},
                    headers=headers,
                )
                resp.raise_for_status()
                data = resp.json()
                results: list[SearchResult] = []

                for item in data.get("items", [])[:5]:
                    repo_name = str(item.get("repository", {}).get("full_name", ""))
                    path = str(item.get("path", ""))
                    gh_url = str(item.get("html_url", ""))

                    # Try fetching a snippet from the file content
                    snippet = f"{repo_name}/{path}"
                    try:
                        file_resp = await client.get(item.get("url", ""), headers=headers)
                        if file_resp.status_code == 200:
                            content_b64 = file_resp.json().get("content", "")
                            if content_b64:
                                import base64
                                decoded = base64.b64decode(content_b64).decode("utf-8", errors="replace")
                                snippet = decoded[:500]
                    except Exception:
                        pass

                    results.append(SearchResult(
                        source="github",
                        title=f"{repo_name}: {path}",
                        snippet=snippet,
                        url=gh_url,
                        relevance_score=float(item.get("score", 0.65)) if item.get("score") is not None else 0.65,
                        metadata={
                            "repo": repo_name,
                            "path": path,
                            "git_url": str(item.get("git_url", "")),
                        },
                    ))
                return results or self._mock_search(query)
        except Exception as e:
            logger.warning(f"GitHub API failed: {e}")
            return self._mock_search(query) if settings.retrieval_fallback_to_mock else []


# ---------------------------------------------------------------------------
# HTML stripping utility
# ---------------------------------------------------------------------------

def _strip_html(text: str) -> str:
    """Remove HTML tags from text."""
    import re
    clean = re.sub(r"<[^>]+>", " ", text)
    clean = re.sub(r"\s+", " ", clean)
    return clean.strip()


# ---------------------------------------------------------------------------
# Orchestrator — parallel multi-source search with degradation
# ---------------------------------------------------------------------------

class RetrievalOrchestrator:
    """Orchestrates parallel search across multiple sources with per-source enable/disable."""

    def __init__(self) -> None:
        self.official_doc = OfficialDocAdapter()
        self.stackoverflow = StackOverflowAdapter()
        self.github = GitHubAdapter()

    def _enabled_sources(self) -> list[str]:
        return [s.strip() for s in settings.retrieval_sources_enabled.split(",") if s.strip()]

    def _adapter_for(self, source: str) -> SearchAdapter | None:
        mapping: dict[str, SearchAdapter] = {
            "official_doc": self.official_doc,
            "stackoverflow": self.stackoverflow,
            "github": self.github,
        }
        return mapping.get(source)

    async def single_source_search(self, source: str, query: str) -> list[SearchResult]:
        adapter = self._adapter_for(source)
        if adapter is None:
            logger.warning(f"Unknown source: {source}")
            return []
        return await adapter.search(query)

    async def multi_source_search(self, query: str, tenant_id: str = "") -> list[SearchResult]:
        enabled = self._enabled_sources()
        if not enabled:
            logger.warning("No retrieval sources enabled")
            return []

        tasks: dict[str, asyncio.Task[list[SearchResult]]] = {}
        for source in enabled:
            adapter = self._adapter_for(source)
            if adapter:
                tasks[source] = asyncio.create_task(adapter.search(query), name=f"search_{source}")

        valid: list[SearchResult] = []
        for source, task in tasks.items():
            try:
                results = await task
                if isinstance(results, list):
                    valid.extend(results)
            except Exception as e:
                logger.warning(f"Search source {source} failed: {e}")

        return _result_parser.merge_results(_result_parser.rank_results(valid))


retrieval_orchestrator = RetrievalOrchestrator()
