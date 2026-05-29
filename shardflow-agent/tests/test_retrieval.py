import pytest

from app.layers.retrieval.retrieval_orchestrator import retrieval_orchestrator
from app.layers.tool.http_executor import http_executor
from app.layers.tool.result_parser import result_parser
from app.layers.tool.tool_registry import tool_registry
from app.models.search_result import SearchResult, ToolMetadata


class TestToolRegistry:
    def test_list_all_returns_seven_tools(self):
        tools = tool_registry.list_all()
        assert len(tools) == 7

    def test_get_known_tool(self):
        tool = tool_registry.get("read_file")
        assert tool.name == "read_file"

    def test_get_unknown_tool_raises(self):
        with pytest.raises(KeyError):
            tool_registry.get("nonexistent")

    def test_validate_input_valid(self):
        tool_registry.register(ToolMetadata(
            name="test_tool", description="test",
            input_schema={"required": ["query"]},
        ))
        assert tool_registry.validate_input("test_tool", {"query": "hello"}) is True

    def test_validate_input_missing_required(self):
        tool_registry.register(ToolMetadata(
            name="test_tool2", description="test",
            input_schema={"required": ["query"]},
        ))
        assert tool_registry.validate_input("test_tool2", {}) is False


class TestHttpExecutor:
    @pytest.mark.asyncio
    async def test_execute_returns_tool_result(self):
        result = await http_executor.execute("search_code", {"query": "test"})
        assert result.tool_name == "search_code"
        assert isinstance(result.success, bool)

    @pytest.mark.asyncio
    async def test_execute_with_retry(self):
        result = await http_executor.execute_with_retry("search_code", {"query": "test"}, retries=1)
        assert result.tool_name == "search_code"


class TestResultParser:
    def test_parse_official_doc(self):
        result = result_parser.parse(
            {"title": "Spring Boot", "snippet": "spring docs", "url": "https://spring.io", "score": 0.9},
            "official_doc"
        )
        assert result.source == "official_doc"
        assert result.title == "Spring Boot"

    def test_parse_stackoverflow(self):
        result = result_parser.parse({
            "items": [{"title": "How to", "body": "answer here", "link": "https://so.com", "score": 0.8}]
        }, "stackoverflow")
        assert result.source == "stackoverflow"

    def test_parse_github(self):
        result = result_parser.parse({
            "items": [{"name": "repo", "html_url": "https://gh.com", "score": 0.7,
                       "text_matches": [{"fragment": "code here"}]}]
        }, "github")
        assert result.source == "github"

    def test_merge_removes_duplicates(self):
        r1 = SearchResult(source="a", title="t", snippet="s", url="http://same")
        r2 = SearchResult(source="b", title="t2", snippet="s2", url="http://same")
        merged = result_parser.merge_results([r1, r2])
        assert len(merged) == 1

    def test_rank_sorts_by_score(self):
        r1 = SearchResult(source="a", title="t", snippet="s", url="http://1", relevance_score=0.3)
        r2 = SearchResult(source="b", title="t2", snippet="s2", url="http://2", relevance_score=0.9)
        ranked = result_parser.rank_results([r1, r2])
        assert ranked[0].relevance_score == 0.9


class TestRetrievalOrchestrator:
    @pytest.mark.asyncio
    async def test_multi_source_search_returns_results(self):
        results = await retrieval_orchestrator.multi_source_search("Dubbo registry")
        assert len(results) > 0
        for r in results:
            assert isinstance(r, SearchResult)
            assert r.source in ("official_doc", "stackoverflow", "github")

    @pytest.mark.asyncio
    async def test_results_are_ranked(self):
        results = await retrieval_orchestrator.multi_source_search("test")
        scores = [r.relevance_score for r in results]
        assert scores == sorted(scores, reverse=True)
