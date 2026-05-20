from typing import Any

from app.infrastructure.callback_client import callback_client
from app.models.strategy import StrategyRecord


class ReuseDecision:
    def __init__(self, decision: str, matched_record: StrategyRecord | None = None,
                 similarity: float = 0.0, suggested_sources: list[str] | None = None,
                 default_strategy: dict[str, Any] | None = None):
        self.decision = decision
        self.matched_record = matched_record
        self.similarity = similarity
        self.suggested_sources = suggested_sources or []
        self.default_strategy = default_strategy


DEFAULT_STRATEGIES: dict[str, dict[str, Any]] = {
    "microservice_auth_exploration": {
        "sources": ["code_comments", "official_doc", "stackoverflow"],
        "weights": {"code_comments": 0.5, "official_doc": 0.3, "stackoverflow": 0.2},
    },
    "dependency_chain_analysis": {
        "sources": ["code_comments", "github_issues", "official_doc"],
        "weights": {"code_comments": 0.6, "github_issues": 0.2, "official_doc": 0.2},
    },
    "performance_optimization": {
        "sources": ["official_doc", "stackoverflow", "github_issues"],
        "weights": {"official_doc": 0.4, "stackoverflow": 0.3, "github_issues": 0.3},
    },
    "api_design_analysis": {
        "sources": ["official_doc", "code_comments", "github_issues"],
        "weights": {"official_doc": 0.5, "code_comments": 0.3, "github_issues": 0.2},
    },
    "error_troubleshooting": {
        "sources": ["stackoverflow", "github_issues", "official_doc"],
        "weights": {"stackoverflow": 0.4, "github_issues": 0.4, "official_doc": 0.2},
    },
    "config_analysis": {
        "sources": ["code_comments", "official_doc"],
        "weights": {"code_comments": 0.7, "official_doc": 0.3},
    },
    "database_schema_exploration": {
        "sources": ["code_comments", "official_doc"],
        "weights": {"code_comments": 0.5, "official_doc": 0.5},
    },
    "general_code_exploration": {
        "sources": ["code_comments", "official_doc", "stackoverflow"],
        "weights": {"code_comments": 0.4, "official_doc": 0.3, "stackoverflow": 0.3},
    },
}


class StrategyEngine:
    def __init__(self) -> None:
        self._records: list[StrategyRecord] = []

    async def search_strategy(self, task_type: str, query_pattern: str,
                              query_embedding: list[float] | None = None,
                              limit: int = 5) -> list[tuple[StrategyRecord, float]]:
        results: list[tuple[StrategyRecord, float]] = []
        for record in self._records:
            if record.task_type == task_type:
                sim = 0.95
                results.append((record, sim))
            elif query_embedding and record.embedding:
                sim = self._cosine_similarity(query_embedding, record.embedding)
                if sim > 0.7:
                    results.append((record, sim))

        results.sort(key=lambda x: x[1], reverse=True)
        return results[:limit]

    def score_strategy(self, record: StrategyRecord, context: dict[str, Any]) -> float:
        similarity = context.get("similarity", 0.5)
        source_reliability = 0.0
        if record.source_combo:
            source_reliability = sum(s.weight * s.reliability for s in record.source_combo) / len(record.source_combo)
        user_feedback_score = 0.5
        if record.success_score > 0:
            user_feedback_score = record.success_score

        result: float = similarity * 0.4 + source_reliability * 0.3 + user_feedback_score * 0.3
        return result

    def reuse_decision(self, scores: list[tuple[StrategyRecord, float]]) -> ReuseDecision:
        if not scores:
            return ReuseDecision("COLD_START", default_strategy=DEFAULT_STRATEGIES.get(
                "general_code_exploration"))

        top_record, top_score = scores[0]
        if top_score > 0.85:
            sources = [s.source for s in top_record.source_combo]
            return ReuseDecision("AUTO_REUSE", top_record, top_score, suggested_sources=sources)
        elif top_score >= 0.70:
            sources = [s.source for s in top_record.source_combo]
            return ReuseDecision("PROMPT_USER", top_record, top_score, suggested_sources=sources)
        else:
            return ReuseDecision("COLD_START", default_strategy=DEFAULT_STRATEGIES.get(
                top_record.task_type, DEFAULT_STRATEGIES["general_code_exploration"]))

    def get_default_strategy(self, task_type: str) -> dict[str, Any]:
        return DEFAULT_STRATEGIES.get(task_type, DEFAULT_STRATEGIES["general_code_exploration"])

    async def save_strategy(self, record: StrategyRecord) -> str:
        self._records.append(record)
        await callback_client.save_strategy(record.model_dump())
        return record.strategy_id

    def _cosine_similarity(self, a: list[float], b: list[float]) -> float:
        if not a or not b or len(a) != len(b):
            return 0.0
        dot = sum(x * y for x, y in zip(a, b))
        norm_a = sum(x ** 2 for x in a) ** 0.5
        norm_b = sum(x ** 2 for x in b) ** 0.5
        if norm_a == 0 or norm_b == 0:
            return 0.0
        result: float = dot / (norm_a * norm_b)
        return result


strategy_engine = StrategyEngine()
