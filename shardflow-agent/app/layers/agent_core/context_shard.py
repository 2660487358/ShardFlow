import json
from typing import Any

from app.layers.agent_core.llm_router import llm_router
from app.layers.agent_core.prompt_engine import prompt_engine
from app.infrastructure.shard_cache import shard_cache
from app.models.context_shard import ContextShard, ExplorationDepth, KeyDecision


class ConflictInfo:
    def __init__(self, conflict_type: str, field: str, previous_value: str,
                 current_value: str, semantic_similarity: float, severity: str):
        self.conflict_type = conflict_type
        self.field = field
        self.previous_value = previous_value
        self.current_value = current_value
        self.semantic_similarity = semantic_similarity
        self.severity = severity


class ContextShardManager:
    async def extract_shard(self, state: dict[str, Any]) -> ContextShard | None:
        usage = state.get("context_usage_ratio", 0)
        if usage < 0.80:
            return None

        messages = state.get("messages", [])
        history = json.dumps([m.get("content", "") for m in messages[-20:]], ensure_ascii=False)
        existing = state.get("context_shard_info", "None")

        prompt = prompt_engine.build_shard_extract_prompt(history, existing)
        for attempt in range(3):
            try:
                model = llm_router.select_model("shard_extract")
                response = await llm_router.call_with_retry(prompt, model)
                content = await llm_router.extract_content(response)
                data = json.loads(content)
                shard = ContextShard(
                    task_id=state.get("task_id", ""),
                    tenant_id=state.get("tenant_id", ""),
                    session_seq=state.get("loop_count", 1),
                    confirmed=data.get("confirmed", []),
                    excluded=data.get("excluded", []),
                    pending=data.get("pending", []),
                    source_preference=state.get("source_preferences", {}),
                    exploration_depth=state.get("exploration_depth", ExplorationDepth.SERVICE_LEVEL),
                    key_decisions=[KeyDecision(**d) for d in data.get("key_decisions", [])],
                )
                await shard_cache.save_shard(state.get("tenant_id", ""), shard.model_dump())
                return shard
            except Exception:
                if attempt == 2:
                    return None
        return None

    def inject_shard(self, shard: ContextShard, state: dict[str, Any]) -> str:
        parts: list[str] = []
        parts.append("【上下文继承自上一次探索会话】\n")

        if shard.confirmed:
            parts.append("已确认的知识点：")
            for item in shard.confirmed:
                fact = item.get("fact", str(item))
                confidence = item.get("confidence", "?")
                parts.append(f"  - {fact}（置信度 {confidence}）")

        if shard.excluded:
            parts.append("\n已排除的假设：")
            for ex in shard.excluded:
                hypothesis = ex.get("hypothesis", str(ex))
                reason = ex.get("reason", "")
                parts.append(f"  - {hypothesis}（原因：{reason}）")

        if shard.pending:
            parts.append("\n待探索的问题：")
            for p in shard.pending:
                parts.append(f"  - {p}")

        if shard.source_preference:
            prefs = ", ".join(f"{k}: {v}" for k, v in shard.source_preference.items())
            parts.append(f"\n信息来源偏好：{prefs}")

        if shard.key_decisions:
            parts.append("\n关键决策：")
            for kd in shard.key_decisions:
                parts.append(f"  - {kd.decision}（原因：{kd.reason}；置信度 {kd.confidence}）")

        parts.append(f"\n当前探索粒度：{shard.exploration_depth.value}")
        parts.append("\n请继续探索上述待完成的问题。")

        return "\n".join(parts)

    def check_conflict(self, current: ContextShard, previous: ContextShard) -> list[ConflictInfo]:
        conflicts: list[ConflictInfo] = []

        current_facts = {item.get("fact", str(item)): item for item in current.confirmed}
        prev_facts = {item.get("fact", str(item)): item for item in previous.confirmed}
        for key, cur_val in current_facts.items():
            if key in prev_facts:
                cur_conf = cur_val.get("confidence", 0)
                prev_conf = prev_facts[key].get("confidence", 0)
                if abs(cur_conf - prev_conf) > 0.5:
                    conflicts.append(ConflictInfo(
                        "confirmed_contradiction", "confirmed",
                        f"{key} ({prev_conf})", f"{key} ({cur_conf})",
                        0.3, "high",
                    ))

        prev_excluded = {item.get("hypothesis", str(item)) for item in previous.excluded}
        cur_confirmed_set = {item.get("fact", str(item)) for item in current.confirmed}
        reactivated = cur_confirmed_set & prev_excluded
        for item in reactivated:
            conflicts.append(ConflictInfo(
                "excluded_reactivation", "excluded",
                item, f"reactivated: {item}",
                0.1, "medium",
            ))

        return conflicts

    def merge_shard(self, current: ContextShard, previous: ContextShard,
                    user_decision: str = "AUTO_MERGE") -> ContextShard:
        if user_decision == "KEEP_PREVIOUS":
            return previous
        if user_decision == "ACCEPT_CURRENT":
            return current

        merged_confirmed = list(previous.confirmed)
        existing_facts: dict[str, dict[str, Any]] = {
            item.get("fact", str(item)): item for item in merged_confirmed
        }
        for item in current.confirmed:
            fact = item.get("fact", str(item))
            if fact not in existing_facts:
                merged_confirmed.append(item)
            elif item.get("confidence", 0) > existing_facts[fact].get("confidence", 0):
                merged_confirmed = [
                    item if c.get("fact", str(c)) == fact else c for c in merged_confirmed
                ]

        merged_excluded = list(previous.excluded)
        existing_hypotheses = {item.get("hypothesis", str(item)) for item in merged_excluded}
        for item in current.excluded:
            if item.get("hypothesis", str(item)) not in existing_hypotheses:
                merged_excluded.append(item)

        merged_pending = list(set(previous.pending + current.pending))

        dest = current if current.exploration_depth.value >= previous.exploration_depth.value else previous
        merged_depth = dest.exploration_depth

        return ContextShard(
            task_id=current.task_id,
            tenant_id=current.tenant_id,
            session_seq=current.session_seq,
            confirmed=merged_confirmed,
            excluded=merged_excluded,
            pending=merged_pending,
            source_preference=current.source_preference or previous.source_preference,
            exploration_depth=merged_depth,
            key_decisions=previous.key_decisions + current.key_decisions,
        )


context_shard_manager = ContextShardManager()
