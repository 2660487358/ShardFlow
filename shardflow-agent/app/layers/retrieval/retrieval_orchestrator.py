import asyncio
import logging

from app.layers.tool.result_parser import result_parser as _result_parser
from app.models.search_result import SearchResult

logger = logging.getLogger(__name__)


class SearchAdapter:
    async def search(self, query: str) -> list[SearchResult]:
        return []


class OfficialDocAdapter(SearchAdapter):
    async def search(self, query: str) -> list[SearchResult]:
        try:
            return [SearchResult(
                source="official_doc",
                title=f"Official docs: {query}",
                snippet=f"Documentation results for: {query}",
                url=f"https://docs.example.com/search?q={query}",
                relevance_score=0.7,
            )]
        except Exception:
            return []


class StackOverflowAdapter(SearchAdapter):
    async def search(self, query: str) -> list[SearchResult]:
        try:
            return [SearchResult(
                source="stackoverflow",
                title=f"StackOverflow: {query}",
                snippet=f"Community answers for: {query}",
                url=f"https://stackoverflow.com/search?q={query}",
                relevance_score=0.6,
            )]
        except Exception:
            return []


class GitHubAdapter(SearchAdapter):
    async def search(self, query: str) -> list[SearchResult]:
        try:
            return [SearchResult(
                source="github",
                title=f"GitHub: {query}",
                snippet=f"Code search results for: {query}",
                url=f"https://github.com/search?q={query}",
                relevance_score=0.65,
            )]
        except Exception:
            return []


class RetrievalOrchestrator:
    def __init__(self) -> None:
        self.official_doc = OfficialDocAdapter()
        self.stackoverflow = StackOverflowAdapter()
        self.github = GitHubAdapter()

    async def multi_source_search(self, query: str, tenant_id: str = "") -> list[SearchResult]:
        tasks = [
            self.official_doc.search(query),
            self.stackoverflow.search(query),
            self.github.search(query),
        ]
        gathered = await asyncio.gather(*tasks, return_exceptions=True)

        valid: list[SearchResult] = []
        for r in gathered:
            if isinstance(r, Exception):
                logger.warning(f"Search source failed: {r}")
                continue
            if isinstance(r, list):
                valid.extend(r)

        return _result_parser.merge_results(_result_parser.rank_results(valid))


retrieval_orchestrator = RetrievalOrchestrator()
