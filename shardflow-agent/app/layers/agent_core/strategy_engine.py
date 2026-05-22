"""Strategy Engine: semantic retrieval, scoring, reuse decisions.

Phase 2 update: search_strategy now proxies through Java kb-strategy service
for pgvector semantic search. Local cache serves as fallback.
"""
from typing import Any

from app.infrastructure.callback_client import callback_client
from app.models.strategy import SourceCombo, StrategyRecord


class ReuseDecision:
    def __init__(self, decision: str, matched_record: StrategyRecord | None = None,
                 similarity: float = 0.0, suggested_sources: list[str] | None = None,
                 default_strategy: dict[str, Any] | None = None):
        self.decision = decision
        self.matched_record = matched_record
        self.similarity = similarity
        self.suggested_sources = suggested_sources or []
        self.default_strategy = default_strategy


# tool_combo 元素格式: {"name": str, "source": "builtin"|"mcp"}
# 保留旧 string[] 格式兼容：get_default_strategy() 会同时返回 tool_combo 和 tool_combo_annotated
DEFAULT_STRATEGIES: dict[str, dict[str, Any]] = {
    # ═══════════════════════════════════════════════════════════
    # 知识获取（通用）
    # ═══════════════════════════════════════════════════════════
    "technology_research": {
        "sources": ["web_search", "official_doc", "github"],
        "weights": {"web_search": 0.5, "official_doc": 0.3, "github": 0.2},
        "tool_combo": [
            {"name": "web_search", "source": "mcp"},
            {"name": "read_file", "source": "builtin"},
        ],
    },
    "web_search": {
        "sources": ["web_search"],
        "weights": {"web_search": 1.0},
        "tool_combo": [
            {"name": "web_search", "source": "mcp"},
        ],
    },
    "knowledge_qa": {
        "sources": ["web_search", "official_doc"],
        "weights": {"web_search": 0.6, "official_doc": 0.4},
        "tool_combo": [
            {"name": "web_search", "source": "mcp"},
        ],
    },

    # ═══════════════════════════════════════════════════════════
    # 文档写作（通用）
    # ═══════════════════════════════════════════════════════════
    "doc_writing": {
        "sources": ["web_search", "official_doc", "read_file"],
        "weights": {"web_search": 0.4, "official_doc": 0.3, "read_file": 0.3},
        "tool_combo": [
            {"name": "read_file", "source": "builtin"},
            {"name": "web_search", "source": "mcp"},
            {"name": "write_file", "source": "builtin"},
        ],
    },
    "code_generation": {
        "sources": ["code_analyze", "github", "official_doc"],
        "weights": {"code_analyze": 0.4, "github": 0.3, "official_doc": 0.3},
        "tool_combo": [
            {"name": "read_file", "source": "builtin"},
            {"name": "code_analyze", "source": "builtin"},
            {"name": "write_file", "source": "builtin"},
        ],
    },

    # ═══════════════════════════════════════════════════════════
    # 任务管理（通用）
    # ═══════════════════════════════════════════════════════════
    "task_planning": {
        "sources": ["web_search", "read_file"],
        "weights": {"web_search": 0.6, "read_file": 0.4},
        "tool_combo": [
            {"name": "web_search", "source": "mcp"},
            {"name": "read_file", "source": "builtin"},
        ],
    },
    "schedule_management": {
        "sources": ["web_search"],
        "weights": {"web_search": 1.0},
        "tool_combo": [
            {"name": "web_search", "source": "mcp"},
        ],
    },
    "file_management": {
        "sources": ["read_file"],
        "weights": {"read_file": 1.0},
        "tool_combo": [
            {"name": "read_file", "source": "builtin"},
            {"name": "write_file", "source": "builtin"},
        ],
    },

    # ═══════════════════════════════════════════════════════════
    # 代码相关（@Deprecated — 保留为子集，新任务优先使用通用策略）
    # ═══════════════════════════════════════════════════════════
    "microservice_auth_exploration": {
        "sources": ["code_comments", "official_doc", "stackoverflow"],
        "weights": {"code_comments": 0.5, "official_doc": 0.3, "stackoverflow": 0.2},
        "tool_combo": [
            {"name": "read_file", "source": "builtin"},
            {"name": "code_analyze", "source": "builtin"},
        ],
        "_deprecated": True,
    },
    "dependency_chain_analysis": {
        "sources": ["code_comments", "github_issues", "official_doc"],
        "weights": {"code_comments": 0.6, "github_issues": 0.2, "official_doc": 0.2},
        "tool_combo": [
            {"name": "read_file", "source": "builtin"},
            {"name": "code_analyze", "source": "builtin"},
        ],
        "_deprecated": True,
    },
    "performance_optimization": {
        "sources": ["official_doc", "stackoverflow", "github_issues"],
        "weights": {"official_doc": 0.4, "stackoverflow": 0.3, "github_issues": 0.3},
        "tool_combo": [
            {"name": "read_file", "source": "builtin"},
            {"name": "code_analyze", "source": "builtin"},
            {"name": "web_search", "source": "mcp"},
        ],
        "_deprecated": True,
    },
    "api_design_analysis": {
        "sources": ["official_doc", "code_comments", "github_issues"],
        "weights": {"official_doc": 0.5, "code_comments": 0.3, "github_issues": 0.2},
        "tool_combo": [
            {"name": "read_file", "source": "builtin"},
            {"name": "code_analyze", "source": "builtin"},
        ],
        "_deprecated": True,
    },
    "error_troubleshooting": {
        "sources": ["stackoverflow", "github_issues", "official_doc"],
        "weights": {"stackoverflow": 0.4, "github_issues": 0.4, "official_doc": 0.2},
        "tool_combo": [
            {"name": "read_file", "source": "builtin"},
            {"name": "code_analyze", "source": "builtin"},
            {"name": "web_search", "source": "mcp"},
        ],
        "_deprecated": True,
    },
    "config_analysis": {
        "sources": ["code_comments", "official_doc"],
        "weights": {"code_comments": 0.7, "official_doc": 0.3},
        "tool_combo": [
            {"name": "read_file", "source": "builtin"},
        ],
        "_deprecated": True,
    },
    "database_schema_exploration": {
        "sources": ["code_comments", "official_doc"],
        "weights": {"code_comments": 0.5, "official_doc": 0.5},
        "tool_combo": [
            {"name": "read_file", "source": "builtin"},
            {"name": "code_analyze", "source": "builtin"},
        ],
        "_deprecated": True,
    },
    "general_code_exploration": {
        "sources": ["code_comments", "official_doc", "stackoverflow"],
        "weights": {"code_comments": 0.4, "official_doc": 0.3, "stackoverflow": 0.3},
        "tool_combo": [
            {"name": "read_file", "source": "builtin"},
            {"name": "code_analyze", "source": "builtin"},
        ],
        "_deprecated": True,
    },
    "architecture_design": {
        "sources": ["official_doc", "github", "web_search"],
        "weights": {"official_doc": 0.4, "github": 0.3, "web_search": 0.3},
        "tool_combo": [
            {"name": "read_file", "source": "builtin"},
            {"name": "code_analyze", "source": "builtin"},
            {"name": "web_search", "source": "mcp"},
        ],
        "_deprecated": True,
    },

    # ═══════════════════════════════════════════════════════════
    # 交互协作（通用）
    # ═══════════════════════════════════════════════════════════
    "session_resume": {
        "sources": ["read_file"],
        "weights": {"read_file": 1.0},
        "tool_combo": [
            {"name": "read_file", "source": "builtin"},
        ],
    },
    "communication": {
        "sources": [],
        "weights": {},
        "tool_combo": [],
    },
    "user_feedback": {
        "sources": [],
        "weights": {},
        "tool_combo": [],
    },
    "notification": {
        "sources": [],
        "weights": {},
        "tool_combo": [],
    },

    # ═══════════════════════════════════════════════════════════
    # 兜底
    # ═══════════════════════════════════════════════════════════
    "general_qa": {
        "sources": ["web_search"],
        "weights": {"web_search": 1.0},
        "tool_combo": [
            {"name": "web_search", "source": "mcp"},
        ],
    },
}


class StrategyEngine:
    """Strategy semantic retrieval and reuse engine.

    Search path: Java kb-strategy pgvector API → local cache fallback.
    """

    def __init__(self) -> None:
        self._local_cache: list[StrategyRecord] = []

    async def search_strategy(self, task_type: str, query_pattern: str,
                              query_embedding: list[float] | None = None,
                              limit: int = 5) -> list[tuple[StrategyRecord, float]]:
        """Search strategies via Java proxy (pgvector), fall back to local cache."""
        # Try Java kb-strategy API first
        try:
            proxy_results = await callback_client.search_strategies(
                task_type=task_type,
                query=query_pattern,
                embedding=query_embedding,
                limit=limit,
            )
            if proxy_results:
                records: list[tuple[StrategyRecord, float]] = []
                for item in proxy_results:
                    record = StrategyRecord(**item.get("record", item))
                    score = float(item.get("similarity", 0.5))
                    records.append((record, score))
                records.sort(key=lambda x: x[1], reverse=True)
                if records:
                    return records[:limit]
        except Exception:
            pass  # Fall through to local cache

        # Local cache fallback (also used when Java service unavailable)
        results: list[tuple[StrategyRecord, float]] = []
        for record in self._local_cache:
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
        """Save strategy to local cache and Java kb-strategy service."""
        self._local_cache.append(record)
        try:
            await callback_client.save_strategy(record.model_dump())
        except Exception:
            pass  # Local cache persists even if Java unavailable
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
