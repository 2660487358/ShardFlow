import pytest

from app.layers.agent_core.strategy_engine import DEFAULT_STRATEGIES, StrategyEngine, strategy_engine
from app.models.strategy import SourceCombo, StrategyRecord


def _make_record(task_type: str = "microservice_auth_exploration",
                 success_score: float = 0.85) -> StrategyRecord:
    return StrategyRecord(
        strategy_id="sr-001", user_id="u1", task_type=task_type,
        query_pattern="explore auth",
        source_combo=[
            SourceCombo(source="code_comments", weight=0.5, reliability=0.9),
            SourceCombo(source="official_doc", weight=0.3, reliability=0.7),
        ],
        success_score=success_score, cost_ms=1200,
        embedding=[0.1, 0.2, 0.3],
    )


class TestStrategyEngine:
    @pytest.mark.asyncio
    async def test_search_strategy_exact_match(self):
        engine = StrategyEngine()
        record = _make_record()
        engine._local_cache.append(record)
        results = await engine.search_strategy("microservice_auth_exploration", "explore auth")
        assert len(results) > 0
        assert results[0][0].task_type == "microservice_auth_exploration"

    @pytest.mark.asyncio
    async def test_search_strategy_no_match(self):
        engine = StrategyEngine()
        results = await engine.search_strategy("nonexistent_type", "query")
        assert len(results) == 0

    def test_score_strategy(self):
        record = _make_record(success_score=0.9)
        score = strategy_engine.score_strategy(record, {"similarity": 0.9})
        assert 0.0 <= score <= 1.0

    def test_reuse_decision_auto_reuse(self):
        record = _make_record()
        decision = strategy_engine.reuse_decision([(record, 0.86)])
        assert decision.decision == "AUTO_REUSE"
        assert len(decision.suggested_sources) > 0

    def test_reuse_decision_prompt_user(self):
        record = _make_record()
        decision = strategy_engine.reuse_decision([(record, 0.75)])
        assert decision.decision == "PROMPT_USER"

    def test_reuse_decision_cold_start(self):
        decision = strategy_engine.reuse_decision([])
        assert decision.decision == "COLD_START"
        assert decision.default_strategy is not None

    def test_reuse_decision_cold_start_low_score(self):
        record = _make_record()
        decision = strategy_engine.reuse_decision([(record, 0.65)])
        assert decision.decision == "COLD_START"

    def test_default_strategies_has_entries(self):
        assert len(DEFAULT_STRATEGIES) > 0

    def test_get_default_strategy_known_type(self):
        strat = strategy_engine.get_default_strategy("error_troubleshooting")
        assert strat is not None
        assert "sources" in strat

    def test_get_default_strategy_unknown_type(self):
        strat = strategy_engine.get_default_strategy("unknown")
        assert strat == DEFAULT_STRATEGIES["general_code_exploration"]

    @pytest.mark.asyncio
    async def test_save_strategy(self):
        engine = StrategyEngine()
        record = _make_record()
        engine._local_cache.append(record)
        assert record.strategy_id == "sr-001"
        assert len(engine._local_cache) == 1
