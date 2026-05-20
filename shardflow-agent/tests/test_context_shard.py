from app.layers.agent_core.context_shard import context_shard_manager
from app.layers.agent_core.shard_decision import shard_decision_gate
from app.models.context_shard import ContextShard, ExplorationDepth, KeyDecision


def _make_shard(task_id: str = "t1", confirmed: list | None = None,
                excluded: list | None = None, pending: list | None = None,
                key_decisions: list | None = None) -> ContextShard:
    return ContextShard(
        task_id=task_id, tenant_id="tenant1", session_seq=1,
        confirmed=confirmed or [],
        excluded=excluded or [],
        pending=pending or [],
        source_preference={"code": 0.9},
        exploration_depth=ExplorationDepth.SERVICE_LEVEL,
        key_decisions=key_decisions or [],
    )


class TestShardDecisionGate:
    def test_should_shard_below_threshold(self):
        assert shard_decision_gate.should_shard({"context_usage_ratio": 0.79}) is False

    def test_should_shard_above_threshold_with_pending(self):
        assert shard_decision_gate.should_shard({
            "context_usage_ratio": 0.81,
            "pending": ["item1"],
        }) is True

    def test_should_shard_above_threshold_no_pending(self):
        assert shard_decision_gate.should_shard({
            "context_usage_ratio": 0.81,
            "pending": [],
        }) is False

    def test_token_budget(self):
        budget = shard_decision_gate.token_budget({"token_count": 1000})
        assert budget > 0

    def test_depth_advisor_service_level(self):
        depth = shard_decision_gate.depth_advisor({"pending": ["a"]})
        assert depth == "SERVICE_LEVEL"

    def test_depth_advisor_method_level(self):
        depth = shard_decision_gate.depth_advisor({"pending": ["a", "b", "c", "d"]})
        assert depth == "METHOD_LEVEL"

    def test_depth_advisor_line_level(self):
        depth = shard_decision_gate.depth_advisor({"pending": ["a"] * 7})
        assert depth == "LINE_LEVEL"


class TestContextShardManager:
    def test_inject_shard_contains_confirmed(self):
        shard = _make_shard(confirmed=[
            {"fact": "Gateway uses JWT", "confidence": 0.95, "evidence": ["pom.xml"]}
        ])
        result = context_shard_manager.inject_shard(shard, {})
        assert "Gateway uses JWT" in result
        assert "上下文继承" in result

    def test_inject_shard_contains_excluded(self):
        shard = _make_shard(excluded=[
            {"hypothesis": "Session auth", "reason": "no dependency found"}
        ])
        result = context_shard_manager.inject_shard(shard, {})
        assert "Session auth" in result

    def test_inject_shard_contains_pending(self):
        shard = _make_shard(pending=["Token refresh chain"])
        result = context_shard_manager.inject_shard(shard, {})
        assert "Token refresh chain" in result

    def test_inject_shard_contains_key_decisions(self):
        shard = _make_shard(key_decisions=[
            KeyDecision(decision="Use JWT", reason="jjwt in pom.xml", confidence=0.95)
        ])
        result = context_shard_manager.inject_shard(shard, {})
        assert "Use JWT" in result
        assert "jjwt" in result

    def test_check_conflict_no_conflict(self):
        cur = _make_shard(confirmed=[{"fact": "A", "confidence": 0.9, "evidence": []}])
        prev = _make_shard(confirmed=[{"fact": "B", "confidence": 0.8, "evidence": []}])
        conflicts = context_shard_manager.check_conflict(cur, prev)
        assert len(conflicts) == 0

    def test_check_conflict_detects_contradiction(self):
        cur = _make_shard(confirmed=[{"fact": "A", "confidence": 0.9, "evidence": []}])
        prev = _make_shard(confirmed=[{"fact": "A", "confidence": 0.1, "evidence": []}])
        conflicts = context_shard_manager.check_conflict(cur, prev)
        assert len(conflicts) > 0

    def test_merge_shard_auto_merge(self):
        cur = _make_shard(confirmed=[{"fact": "New fact", "confidence": 0.9, "evidence": []}])
        prev = _make_shard(confirmed=[{"fact": "Old fact", "confidence": 0.8, "evidence": []}])
        merged = context_shard_manager.merge_shard(cur, prev, "AUTO_MERGE")
        assert len(merged.confirmed) == 2

    def test_merge_shard_keep_previous(self):
        cur = _make_shard(confirmed=[{"fact": "New", "confidence": 0.9, "evidence": []}])
        prev = _make_shard(confirmed=[{"fact": "Old", "confidence": 0.8, "evidence": []}])
        merged = context_shard_manager.merge_shard(cur, prev, "KEEP_PREVIOUS")
        assert merged == prev

    def test_merge_shard_accept_current(self):
        cur = _make_shard(confirmed=[{"fact": "New", "confidence": 0.9, "evidence": []}])
        prev = _make_shard(confirmed=[{"fact": "Old", "confidence": 0.8, "evidence": []}])
        merged = context_shard_manager.merge_shard(cur, prev, "ACCEPT_CURRENT")
        assert merged == cur
