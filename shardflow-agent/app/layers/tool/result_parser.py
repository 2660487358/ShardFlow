from typing import Any

from app.models.search_result import SearchResult


class ResultParser:
    def parse(self, response: dict[str, Any], source_type: str) -> SearchResult:
        if source_type == "official_doc":
            return SearchResult(
                source=source_type,
                title=response.get("title", ""),
                snippet=response.get("snippet", response.get("body", ""))[:500],
                url=response.get("url", ""),
                relevance_score=response.get("score", 0.5),
            )
        elif source_type == "stackoverflow":
            items = response.get("items", [{}])
            item = items[0] if items else {}
            return SearchResult(
                source=source_type,
                title=item.get("title", ""),
                snippet=item.get("body", "")[:500] if item.get("body") else "",
                url=item.get("link", ""),
                relevance_score=item.get("score", 0.5),
            )
        elif source_type == "github":
            items = response.get("items", [{}])
            item = items[0] if items else {}
            return SearchResult(
                source=source_type,
                title=item.get("name", item.get("path", "")),
                snippet=item.get("text_matches", [{}])[0].get("fragment", "")[:500] if item.get("text_matches") else "",
                url=item.get("html_url", ""),
                relevance_score=item.get("score", 0.5),
            )
        else:
            return SearchResult(source=source_type, title="", snippet="", url="")

    def batch_parse(self, results: list[tuple[dict[str, Any], str]]) -> list[SearchResult]:
        return [self.parse(data, source) for data, source in results]

    def merge_results(self, results: list[SearchResult]) -> list[SearchResult]:
        seen: set[str] = set()
        merged: list[SearchResult] = []
        for r in results:
            if r.url not in seen:
                seen.add(r.url)
                merged.append(r)
        return merged

    def rank_results(self, results: list[SearchResult]) -> list[SearchResult]:
        return sorted(results, key=lambda r: r.relevance_score, reverse=True)


result_parser = ResultParser()
