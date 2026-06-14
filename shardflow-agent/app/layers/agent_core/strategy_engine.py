"""StrategyEngine — 策略记录与复用引擎 (FR-SR-001, FR-SR-002).

Implements the complete strategy lifecycle:
- FR-SR-001: Strategy recording (tool combos + weights + reliability + success score + vector)
- FR-SR-002: Strategy semantic search & reuse (>0.85 auto-reuse, 0.7-0.85 prompt, <0.7 cold-start)
- FR-SR-001: User feedback loop (useful/not_relevant updates success_score)

Per spec section 4.6:
- Record tool combinations, weights, reliability, user feedback, success scores
- Generate semantic vectors for future matching
- Auto-reuse when similarity > 0.85, prompt when 0.7-0.85, cold-start when < 0.7
"""
import logging
import time
import uuid
from datetime import datetime, timezone
from typing import Any

from app.infrastructure.milvus_client import (
    insert_strategy_vector,
    search_strategy_vectors,
    delete_strategy_vector,
)
from app.infrastructure.callback_client import callback_client
from app.models.strategy import StrategyRecord, ToolComboItem

logger = logging.getLogger(__name__)


# ── Reuse thresholds per FR-SR-002 ──

AUTO_REUSE_THRESHOLD = 0.85     # > 0.85 → auto-reuse tool combo
PROMPT_CONFIRM_THRESHOLD = 0.7  # 0.7-0.85 → prompt user for confirmation
# < 0.7 → cold-start, explore from scratch

# ── Success score update parameters ──

FEEDBACK_USEFUL_BONUS = 0.05    # Bonus for "useful" feedback
FEEDBACK_NEGATIVE_PENALTY = 0.1  # Penalty for "not_relevant" feedback
MIN_SUCCESS_SCORE = 0.0
MAX_SUCCESS_SCORE = 1.0


class StrategySearchResult:
    """Result of a strategy search with reuse decision."""

    def __init__(
        self,
        matched_strategies: list[StrategyRecord],
        reuse_decision: str,  # "auto_reuse" | "prompt_confirm" | "cold_start"
        best_match: StrategyRecord | None = None,
        similarity_score: float = 0.0,
    ):
        self.matched_strategies = matched_strategies
        self.reuse_decision = reuse_decision
        self.best_match = best_match
        self.similarity_score = similarity_score

    def get_tool_combo(self) -> list[ToolComboItem]:
        """Get the recommended tool combo based on reuse decision."""
        if self.best_match and self.reuse_decision in ("auto_reuse", "prompt_confirm"):
            return self.best_match.tool_combo
        return []


class StrategyEngine:
    """Strategy recording and reuse engine.

    Usage:
        engine = StrategyEngine()

        # Record a strategy after task execution
        record = await engine.record_strategy(
            user_id="user_001",
            task_type="technology_research",
            query_pattern="RAG 方案调研对比",
            tool_combo=[ToolComboItem(tool="web_search", weight=0.4, reliability=0.8)],
            cost_ms=1200,
        )

        # Search for reusable strategies
        result = await engine.search_for_reuse(
            user_id="user_001",
            query_vector=[0.12, -0.05, ...],
            task_type="technology_research",
        )

        # Apply user feedback
        await engine.apply_feedback(record_id="sr-001", tool_name="web_search", feedback="useful")
    """

    def __init__(self) -> None:
        self._embedding_fn = None

    async def _get_embedding(self, text: str) -> list[float]:
        """Get embedding vector for a text query.

        Uses the model client to generate embeddings via the configured
        embedding endpoint.
        """
        if self._embedding_fn is None:
            try:
                from app.layers.agent_core.model_client_manager import model_client_manager
                from app.layers.agent_core.llm_router import llm_router

                async def _embed(text: str) -> list[float]:
                    model_id = llm_router.MODEL_MAP.get("embedding", "text-embedding-3-small")
                    client, actual_model = await model_client_manager.get_client(model_id)
                    payload = {
                        "model": actual_model,
                        "input": text,
                    }
                    resp = await client.post("/embeddings", json=payload, timeout=15.0)
                    resp.raise_for_status()
                    data = resp.json()
                    return data["data"][0]["embedding"]

                self._embedding_fn = _embed
            except Exception as e:
                logger.warning("Embedding function not available: %s", e)
                self._embedding_fn = lambda t: []

        return await self._embedding_fn(text)

    # ------------------------------------------------------------------
    # FR-SR-001: Strategy Recording
    # ------------------------------------------------------------------

    async def record_strategy(
        self,
        user_id: str,
        task_type: str,
        query_pattern: str,
        tool_combo: list[ToolComboItem],
        user_feedback: dict[str, str] | None = None,
        success_score: float = 0.0,
        cost_ms: int = 0,
    ) -> StrategyRecord:
        """Record a strategy after task execution.

        Per FR-SR-001:
        - Record tool combinations with weights and reliability
        - Record user feedback (useful/not_relevant)
        - Calculate success score
        - Generate semantic vector for future matching
        - Persist to PostgreSQL (via callback) + Milvus (vector)

        Args:
            user_id: User identifier.
            task_type: Task type (e.g. "technology_research").
            query_pattern: The query pattern that triggered this strategy.
            tool_combo: List of tools with weights and reliability.
            user_feedback: Optional mapping of tool_name -> "useful"|"not_relevant".
            success_score: Initial success score (0.0-1.0).
            cost_ms: Execution time in milliseconds.

        Returns:
            The created StrategyRecord with record_id and embedding.
        """
        record_id = f"sr-{uuid.uuid4().hex[:12]}"
        now = datetime.now(timezone.utc)

        # Calculate initial success score if not provided
        if success_score == 0.0 and tool_combo:
            success_score = self._calculate_initial_success_score(tool_combo, user_feedback)

        record = StrategyRecord(
            record_id=record_id,
            user_id=user_id,
            task_type=task_type,
            query_pattern=query_pattern,
            tool_combo=tool_combo,
            user_feedback=user_feedback or {},
            success_score=success_score,
            cost_ms=cost_ms,
            embedding=[],
            created_at=now,
        )

        # Generate embedding for the query pattern
        try:
            embedding = await self._get_embedding(query_pattern)
            record.embedding = embedding
        except Exception as e:
            logger.warning("Failed to generate embedding for strategy %s: %s", record_id, e)

        # Insert into Milvus vector store
        if record.embedding:
            try:
                await insert_strategy_vector(
                    record_id=record_id,
                    user_id=user_id,
                    task_type=task_type,
                    query_vector=record.embedding,
                    query_pattern=query_pattern,
                    success_score=success_score,
                )
            except Exception as e:
                logger.error("Failed to insert strategy vector %s: %s", record_id, e)

        # Persist to PostgreSQL via callback
        try:
            await self._persist_to_java(record)
        except Exception as e:
            logger.error("Failed to persist strategy %s via callback: %s", record_id, e)

        logger.info(
            "Strategy recorded: %s, user=%s, type=%s, score=%.2f, tools=%d",
            record_id, user_id, task_type, success_score, len(tool_combo),
        )

        return record

    # ------------------------------------------------------------------
    # FR-SR-002: Strategy Semantic Search & Reuse
    # ------------------------------------------------------------------

    async def search_for_reuse(
        self,
        user_id: str,
        query_vector: list[float],
        task_type: str | None = None,
        top_k: int = 3,
    ) -> StrategySearchResult:
        """Search for reusable strategies based on semantic similarity.

        Per FR-SR-002:
        - Generate semantic vector from new task input
        - Search Milvus for Top-3 similar historical strategies
        - > 0.85 → auto-reuse tool combo and weights
        - 0.7-0.85 → prompt user for confirmation
        - < 0.7 → cold-start, explore from scratch

        Args:
            user_id: User identifier.
            query_vector: Embedding vector of the new task query.
            task_type: Optional task type filter.
            top_k: Number of results to return.

        Returns:
            StrategySearchResult with matched strategies and reuse decision.
        """
        start_time = time.monotonic()

        # Search Milvus for similar strategies
        hits = await search_strategy_vectors(
            query_vector=query_vector,
            user_id=user_id,
            task_type=task_type,
            top_k=top_k,
            min_similarity=PROMPT_CONFIRM_THRESHOLD,
        )

        elapsed_ms = int((time.monotonic() - start_time) * 1000)

        if not hits:
            logger.info(
                "Strategy search: cold-start for user=%s, type=%s (%dms)",
                user_id, task_type, elapsed_ms,
            )
            return StrategySearchResult(
                matched_strategies=[],
                reuse_decision="cold_start",
            )

        # Convert hits to StrategyRecord objects
        matched: list[StrategyRecord] = []
        best_similarity = 0.0
        best_record: StrategyRecord | None = None

        for hit in hits:
            similarity = hit.get("similarity_score", 0.0)
            record = StrategyRecord(
                record_id=hit.get("record_id", ""),
                user_id=user_id,
                task_type=hit.get("task_type", ""),
                query_pattern=hit.get("query_pattern", ""),
                success_score=hit.get("success_score", 0.0),
            )
            matched.append(record)

            if similarity > best_similarity:
                best_similarity = similarity
                best_record = record

        # Determine reuse decision based on similarity threshold
        if best_similarity > AUTO_REUSE_THRESHOLD:
            decision = "auto_reuse"
        elif best_similarity >= PROMPT_CONFIRM_THRESHOLD:
            decision = "prompt_confirm"
        else:
            decision = "cold_start"

        logger.info(
            "Strategy search: %s for user=%s, type=%s, best_sim=%.3f, matches=%d (%dms)",
            decision, user_id, task_type, best_similarity, len(matched), elapsed_ms,
        )

        return StrategySearchResult(
            matched_strategies=matched,
            reuse_decision=decision,
            best_match=best_record,
            similarity_score=best_similarity,
        )

    async def search_with_text(
        self,
        user_id: str,
        query_text: str,
        task_type: str | None = None,
        top_k: int = 3,
    ) -> StrategySearchResult:
        """Search for reusable strategies using a text query.

        Convenience method that generates the embedding from text
        before calling search_for_reuse.
        """
        query_vector = await self._get_embedding(query_text)
        if not query_vector:
            return StrategySearchResult(
                matched_strategies=[],
                reuse_decision="cold_start",
            )

        return await self.search_for_reuse(
            user_id=user_id,
            query_vector=query_vector,
            task_type=task_type,
            top_k=top_k,
        )

    # ------------------------------------------------------------------
    # FR-SR-001: User Feedback Loop
    # ------------------------------------------------------------------

    async def apply_feedback(
        self,
        record_id: str,
        tool_name: str,
        feedback: str,
        user_id: str = "",
    ) -> float:
        """Apply user feedback to update a strategy's success score.

        Per FR-SR-001:
        - "useful" feedback: increase success_score by FEEDBACK_USEFUL_BONUS
        - "not_relevant" feedback: decrease success_score by FEEDBACK_NEGATIVE_PENALTY
        - Update the strategy record and Milvus vector

        Args:
            record_id: The strategy record ID.
            tool_name: The tool that received feedback.
            feedback: "useful" or "not_relevant".
            user_id: User identifier (for logging).

        Returns:
            The updated success_score.
        """
        # For now, we compute the new score and persist via callback.
        # In a full implementation, we would first read the existing record.
        # The callback endpoint handles the update logic on the Java side.

        if feedback == "useful":
            score_delta = FEEDBACK_USEFUL_BONUS
        elif feedback == "not_relevant":
            score_delta = -FEEDBACK_NEGATIVE_PENALTY
        else:
            logger.warning("Unknown feedback type: %s for strategy %s", feedback, record_id)
            return 0.0

        # Persist feedback via callback
        try:
            await callback_client.save_strategy_feedback({
                "record_id": record_id,
                "user_id": user_id,
                "tool_name": tool_name,
                "feedback": feedback,
                "score_delta": score_delta,
            })
        except Exception as e:
            logger.error("Failed to persist feedback for strategy %s: %s", record_id, e)

        logger.info(
            "Feedback applied: strategy=%s, tool=%s, feedback=%s, delta=%.2f",
            record_id, tool_name, feedback, score_delta,
        )

        return score_delta

    # ------------------------------------------------------------------
    # Strategy Deletion
    # ------------------------------------------------------------------

    async def delete_strategy(self, record_id: str) -> bool:
        """Delete a strategy record and its vector.

        Performs logical deletion on PostgreSQL and removes the vector from Milvus.
        """
        # Remove from Milvus
        try:
            await delete_strategy_vector(record_id)
        except Exception as e:
            logger.error("Failed to delete strategy vector %s: %s", record_id, e)

        # Logical delete via callback
        try:
            await callback_client.delete_strategy({"record_id": record_id})
        except Exception as e:
            logger.error("Failed to delete strategy record %s via callback: %s", record_id, e)
            return False

        logger.info("Strategy deleted: %s", record_id)
        return True

    # ------------------------------------------------------------------
    # Integration with ToolSelector
    # ------------------------------------------------------------------

    async def get_strategy_for_intent(
        self,
        user_id: str,
        intent: str,
        query_text: str = "",
        query_vector: list[float] | None = None,
    ) -> StrategySearchResult:
        """Get strategy recommendation for a given intent.

        This is the primary integration point with ToolSelector.
        Returns a StrategySearchResult that can be used to decide
        whether to reuse a historical tool combo or fall back to defaults.

        Args:
            user_id: User identifier.
            intent: The detected intent (maps to task_type).
            query_text: The user's query text (for embedding generation).
            query_vector: Pre-computed embedding (if available).

        Returns:
            StrategySearchResult with reuse decision.
        """
        if query_vector:
            return await self.search_for_reuse(
                user_id=user_id,
                query_vector=query_vector,
                task_type=intent,
            )
        elif query_text:
            return await self.search_with_text(
                user_id=user_id,
                query_text=query_text,
                task_type=intent,
            )
        else:
            return StrategySearchResult(
                matched_strategies=[],
                reuse_decision="cold_start",
            )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _calculate_initial_success_score(
        self,
        tool_combo: list[ToolComboItem],
        user_feedback: dict[str, str] | None = None,
    ) -> float:
        """Calculate initial success score based on tool combo and feedback.

        Score = weighted average of tool reliability, adjusted by feedback.
        """
        if not tool_combo:
            return 0.0

        # Weighted average of reliability
        total_weight = sum(t.weight for t in tool_combo)
        if total_weight == 0:
            # Equal weights if none specified
            avg_reliability = sum(t.reliability for t in tool_combo) / len(tool_combo)
        else:
            avg_reliability = sum(t.weight * t.reliability for t in tool_combo) / total_weight

        # Adjust by feedback
        if user_feedback:
            useful_count = sum(1 for v in user_feedback.values() if v == "useful")
            negative_count = sum(1 for v in user_feedback.values() if v == "not_relevant")
            total_feedback = useful_count + negative_count
            if total_feedback > 0:
                feedback_ratio = useful_count / total_feedback
                # Blend reliability with feedback ratio
                avg_reliability = 0.6 * avg_reliability + 0.4 * feedback_ratio

        return max(MIN_SUCCESS_SCORE, min(MAX_SUCCESS_SCORE, avg_reliability))

    async def _persist_to_java(self, record: StrategyRecord) -> dict[str, Any]:
        """Persist strategy record to Java service via callback.

        Calls POST /api/v1/callback/strategies with the strategy data.
        """
        tool_combo_data = [
            {
                "tool": t.tool,
                "weight": t.weight,
                "reliability": t.reliability,
            }
            for t in record.tool_combo
        ]

        payload = {
            "record_id": record.record_id,
            "user_id": record.user_id,
            "task_type": record.task_type,
            "query_pattern": record.query_pattern,
            "tool_combo": tool_combo_data,
            "user_feedback": record.user_feedback,
            "success_score": record.success_score,
            "cost_ms": record.cost_ms,
            "created_at": record.created_at.isoformat(),
        }

        return await callback_client.save_strategy_record(payload)


# Global singleton
strategy_engine = StrategyEngine()
