"""EpisodicMemoryManager — 情景记忆管理器 (FR-EM-001 ~ FR-EM-003).

Manages episodic memory: decision paths, historical events, and audit trails.

Three core capabilities:
- FR-EM-001: Decision path recording (input → intent → tool call → conclusion → output)
- FR-EM-002: Historical session summary (topic aggregation, semantic search, timeline)
- FR-EM-003: Full-chain traceability & audit (per-task-node traceability, audit logging)

Storage: L0 (local) + L1 (Redis) + L2 (PostgreSQL) via MemoryOrchestrator.
"""
import logging
import uuid
from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, Field

from app.layers.agent_core.memory_orchestrator import memory_orchestrator
from app.models.memory import MemoryType

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data models for episodic memory
# ---------------------------------------------------------------------------

class DecisionStep(BaseModel):
    """A single step in a decision path (FR-EM-001)."""
    step_id: str = Field(default_factory=lambda: uuid.uuid4().hex[:8])
    step_type: str = ""          # input | intent | tool_call | intermediate | conclusion | output
    content: str = ""
    tool_name: str = ""
    tool_input: dict[str, Any] = Field(default_factory=dict)
    tool_output: str = ""
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    confidence: float = 0.0
    metadata: dict[str, Any] = Field(default_factory=dict)


class DecisionPath(BaseModel):
    """Complete decision path for a task (FR-EM-001).

    Records the full chain: input → intent recognition → tool calls →
    intermediate conclusions → final output.
    """
    path_id: str = Field(default_factory=lambda: f"dp_{uuid.uuid4().hex[:12]}")
    user_id: str = ""
    session_id: str = ""
    task_id: str = ""
    task_type: str = ""
    steps: list[DecisionStep] = Field(default_factory=list)
    final_conclusion: str = ""
    started_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    completed_at: datetime | None = None
    total_steps: int = 0
    tools_used: list[str] = Field(default_factory=list)
    success: bool = True

    model_config = {"extra": "allow"}


class HistoricalSessionSummary(BaseModel):
    """Aggregated historical session summary (FR-EM-002).

    Groups related sessions by topic for semantic retrieval and timeline browsing.
    """
    topic: str = ""
    session_ids: list[str] = Field(default_factory=list)
    time_range: dict[str, str] = Field(default_factory=dict)  # start/end ISO strings
    key_decisions: list[str] = Field(default_factory=list)
    tools_used: list[str] = Field(default_factory=list)
    conclusion_summary: str = ""
    relevance_score: float = 0.0

    model_config = {"extra": "allow"}


class TraceNode(BaseModel):
    """A node in the full-chain trace graph (FR-EM-003)."""
    node_id: str = ""
    node_type: str = ""          # task | decision | tool_call | memory_op
    content: str = ""
    parent_node_id: str | None = None
    children_ids: list[str] = Field(default_factory=list)
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    metadata: dict[str, Any] = Field(default_factory=dict)


class TraceChain(BaseModel):
    """Full-chain trace from output back to every decision (FR-EM-003)."""
    trace_id: str = Field(default_factory=lambda: f"tr_{uuid.uuid4().hex[:12]}")
    user_id: str = ""
    task_id: str = ""
    root_node_id: str = ""
    nodes: dict[str, TraceNode] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    model_config = {"extra": "allow"}


# ---------------------------------------------------------------------------
# EpisodicMemoryManager
# ---------------------------------------------------------------------------

class EpisodicMemoryManager:
    """Manages episodic memory: decision paths, historical events, and audit trails.

    All writes go through MemoryOrchestrator for L0→L1→L2 persistence.
    Reads use the same orchestrator with degrade-chain fallback.
    """

    def __init__(self) -> None:
        # L0 cache: active decision paths (session_id -> DecisionPath)
        self._active_paths: dict[str, DecisionPath] = {}
        # L0 cache: active trace chains (task_id -> TraceChain)
        self._active_traces: dict[str, TraceChain] = {}

    # ------------------------------------------------------------------
    # FR-EM-001: Decision path recording
    # ------------------------------------------------------------------

    def start_decision_path(self, user_id: str, session_id: str,
                            task_id: str = "", task_type: str = "",
                            initial_input: str = "") -> DecisionPath:
        """Start recording a new decision path for a task.

        Creates the initial 'input' step and stores the path in L0.
        """
        path = DecisionPath(
            user_id=user_id,
            session_id=session_id,
            task_id=task_id,
            task_type=task_type,
        )

        if initial_input:
            input_step = DecisionStep(
                step_type="input",
                content=initial_input,
                timestamp=datetime.now(timezone.utc),
            )
            path.steps.append(input_step)

        self._active_paths[session_id] = path
        logger.info("Decision path started: path_id=%s, session=%s, task=%s",
                     path.path_id, session_id, task_id)
        return path

    def record_intent(self, session_id: str, intent: str,
                      confidence: float = 0.0) -> DecisionStep | None:
        """Record an intent recognition step in the decision path."""
        path = self._active_paths.get(session_id)
        if path is None:
            logger.warning("No active decision path for session %s", session_id)
            return None

        step = DecisionStep(
            step_type="intent",
            content=intent,
            confidence=confidence,
            timestamp=datetime.now(timezone.utc),
        )
        path.steps.append(step)
        return step

    def record_tool_call(self, session_id: str, tool_name: str,
                         tool_input: dict[str, Any] | None = None,
                         tool_output: str = "",
                         metadata: dict[str, Any] | None = None) -> DecisionStep | None:
        """Record a tool call step in the decision path."""
        path = self._active_paths.get(session_id)
        if path is None:
            logger.warning("No active decision path for session %s", session_id)
            return None

        step = DecisionStep(
            step_type="tool_call",
            content=f"Called tool: {tool_name}",
            tool_name=tool_name,
            tool_input=tool_input or {},
            tool_output=tool_output[:500] if tool_output else "",
            metadata=metadata or {},
            timestamp=datetime.now(timezone.utc),
        )
        path.steps.append(step)

        # Track tools used
        if tool_name and tool_name not in path.tools_used:
            path.tools_used.append(tool_name)

        return step

    def record_intermediate_conclusion(self, session_id: str,
                                       conclusion: str,
                                       confidence: float = 0.0) -> DecisionStep | None:
        """Record an intermediate conclusion in the decision path."""
        path = self._active_paths.get(session_id)
        if path is None:
            return None

        step = DecisionStep(
            step_type="intermediate",
            content=conclusion,
            confidence=confidence,
            timestamp=datetime.now(timezone.utc),
        )
        path.steps.append(step)
        return step

    def record_final_output(self, session_id: str, output: str,
                            success: bool = True) -> DecisionStep | None:
        """Record the final output step and complete the decision path."""
        path = self._active_paths.get(session_id)
        if path is None:
            return None

        step = DecisionStep(
            step_type="output",
            content=output,
            timestamp=datetime.now(timezone.utc),
        )
        path.steps.append(step)

        path.final_conclusion = output
        path.completed_at = datetime.now(timezone.utc)
        path.total_steps = len(path.steps)
        path.success = success

        return step

    async def complete_and_save_decision_path(self, session_id: str) -> dict[str, Any] | None:
        """Complete the decision path and persist to L0+L1+L2.

        Returns the saved data dict, or None if no active path.
        """
        path = self._active_paths.get(session_id)
        if path is None:
            logger.warning("No active decision path for session %s", session_id)
            return None

        # Mark completion if not already done
        if path.completed_at is None:
            path.completed_at = datetime.now(timezone.utc)
            path.total_steps = len(path.steps)

        # Build the episodic memory data
        key = path.path_id
        data = path.model_dump(mode="json")

        # Persist through orchestrator (L0→L1→L2)
        await memory_orchestrator.write_episodic(path.user_id, key, data)

        # Also save a MemoryChunk for structured retrieval
        chunk_data = self._path_to_chunk_data(path)
        chunk_key = f"chunk_{path.path_id}"
        await memory_orchestrator.write_episodic(path.user_id, chunk_key, chunk_data)

        # Audit log
        await self._audit_memory_op(
            user_id=path.user_id,
            session_id=session_id,
            task_id=path.task_id,
            operation="episodic_write",
            target_id=key,
            details={"step_count": path.total_steps, "tools_used": path.tools_used},
        )

        # Remove from active cache
        self._active_paths.pop(session_id, None)

        logger.info("Decision path saved: path_id=%s, steps=%d, tools=%s",
                     key, path.total_steps, path.tools_used)

        return data

    def get_active_path(self, session_id: str) -> DecisionPath | None:
        """Get the active decision path for a session (L0 only)."""
        return self._active_paths.get(session_id)

    async def load_decision_path(self, user_id: str, path_id: str) -> DecisionPath | None:
        """Load a decision path from memory (L0→L1→L2 degrade chain)."""
        data = await memory_orchestrator.read_episodic(user_id, path_id)
        if data is None:
            return None
        try:
            return DecisionPath(**data)
        except Exception as e:
            logger.warning("Failed to deserialize decision path %s: %s", path_id, e)
            return None

    async def search_decision_paths(self, user_id: str, task_type: str = "",
                                     tool_name: str = "",
                                     limit: int = 10) -> list[DecisionPath]:
        """Search decision paths by task type or tool name.

        Uses structured query through MemoryOrchestrator.
        """
        from app.models.memory import MemoryQuery

        query = MemoryQuery(
            memory_type=MemoryType.EPISODIC,
            key_prefix="dp_",
            limit=limit,
        )

        records = await memory_orchestrator.search(user_id, MemoryType.EPISODIC, query)

        results: list[DecisionPath] = []
        for record in records:
            try:
                path = DecisionPath(**record.data)
                # Filter by task_type and tool_name if specified
                if task_type and path.task_type != task_type:
                    continue
                if tool_name and tool_name not in path.tools_used:
                    continue
                results.append(path)
            except Exception:
                continue

        return results

    # ------------------------------------------------------------------
    # FR-EM-002: Historical session summary
    # ------------------------------------------------------------------

    async def get_historical_sessions(self, user_id: str,
                                       topic: str = "",
                                       limit: int = 20) -> list[HistoricalSessionSummary]:
        """Retrieve historical session summaries, optionally filtered by topic.

        S5.6: Enhanced with topic clustering — aggregates related sessions
        by topic/category, supporting semantic retrieval and timeline browsing.

        Aggregates episodic memory entries by topic for timeline browsing.
        """
        from app.models.memory import MemoryQuery

        query = MemoryQuery(
            memory_type=MemoryType.EPISODIC,
            key_prefix="chunk_dp_",
            limit=limit * 3,  # Over-fetch for clustering
        )

        records = await memory_orchestrator.search(user_id, MemoryType.EPISODIC, query)

        # S5.6: Group records by topic/category for true aggregation
        topic_groups: dict[str, list[dict[str, Any]]] = {}
        for record in records:
            try:
                data = record.data
                category = data.get("category", "") or data.get("task_type", "unknown")

                # Filter by topic if specified
                if topic and topic.lower() not in category.lower() and topic.lower() not in data.get("text", "").lower():
                    continue

                if category not in topic_groups:
                    topic_groups[category] = []
                topic_groups[category].append(data)
            except Exception:
                continue

        # S5.6: Build aggregated summaries from topic groups
        summaries: list[HistoricalSessionSummary] = []
        for topic_key, group_data in topic_groups.items():
            # Aggregate session IDs
            session_ids = list({
                d.get("session_id", "") for d in group_data if d.get("session_id")
            })

            # Aggregate key decisions
            key_decisions: list[str] = []
            for d in group_data:
                decisions = d.get("key_decisions", [])
                if isinstance(decisions, list):
                    for dec in decisions:
                        if dec and dec not in key_decisions:
                            key_decisions.append(dec)

            # Aggregate tools used
            tools_used: list[str] = []
            for d in group_data:
                tools = d.get("tools_used", [])
                if isinstance(tools, list):
                    for tool in tools:
                        if tool and tool not in tools_used:
                            tools_used.append(tool)

            # Compute time range
            timestamps = sorted([
                d.get("created_at", "") for d in group_data if d.get("created_at")
            ])
            time_range = {
                "start": timestamps[0] if timestamps else "",
                "end": timestamps[-1] if timestamps else "",
            }

            # Build conclusion summary from all sessions in the group
            conclusion_parts = [
                d.get("text", "")[:100] for d in group_data if d.get("text")
            ]
            conclusion_summary = " | ".join(conclusion_parts)[:500]

            # Relevance score: based on group size and average confidence
            avg_confidence = sum(
                d.get("confidence", 0.7) for d in group_data
            ) / len(group_data) if group_data else 0.0
            relevance_score = min(1.0, avg_confidence * 0.7 + len(group_data) * 0.1)

            summaries.append(HistoricalSessionSummary(
                topic=topic_key,
                session_ids=session_ids,
                time_range=time_range,
                key_decisions=key_decisions[:10],
                tools_used=tools_used,
                conclusion_summary=conclusion_summary,
                relevance_score=relevance_score,
            ))

        # Sort by relevance score descending
        summaries.sort(key=lambda s: s.relevance_score, reverse=True)
        return summaries[:limit]

    async def get_session_timeline(self, user_id: str,
                                    start_time: datetime | None = None,
                                    end_time: datetime | None = None,
                                    limit: int = 50) -> list[dict[str, Any]]:
        """Get a timeline of episodic events for a user.

        Returns events sorted by time, optionally filtered by date range.
        """
        from app.models.memory import MemoryQuery

        query = MemoryQuery(
            memory_type=MemoryType.EPISODIC,
            created_after=start_time,
            created_before=end_time,
            limit=limit,
        )

        records = await memory_orchestrator.search(user_id, MemoryType.EPISODIC, query)

        timeline: list[dict[str, Any]] = []
        for record in records:
            timeline.append({
                "key": record.key,
                "data": record.data,
                "created_at": record.created_at.isoformat() if record.created_at else "",
            })

        # Sort by created_at descending (most recent first)
        timeline.sort(key=lambda e: e["created_at"], reverse=True)
        return timeline

    # ------------------------------------------------------------------
    # FR-EM-003: Full-chain traceability & audit
    # ------------------------------------------------------------------

    def start_trace(self, user_id: str, task_id: str,
                    root_content: str = "") -> TraceChain:
        """Start a new trace chain for a task."""
        root_node = TraceNode(
            node_id=f"tn_{uuid.uuid4().hex[:8]}",
            node_type="task",
            content=root_content,
        )

        chain = TraceChain(
            user_id=user_id,
            task_id=task_id,
            root_node_id=root_node.node_id,
            nodes={root_node.node_id: root_node},
        )

        self._active_traces[task_id] = chain
        return chain

    def add_trace_node(self, task_id: str, node_type: str,
                       content: str, parent_node_id: str | None = None,
                       metadata: dict[str, Any] | None = None) -> TraceNode | None:
        """Add a node to the active trace chain."""
        chain = self._active_traces.get(task_id)
        if chain is None:
            logger.warning("No active trace chain for task %s", task_id)
            return None

        node = TraceNode(
            node_id=f"tn_{uuid.uuid4().hex[:8]}",
            node_type=node_type,
            content=content,
            parent_node_id=parent_node_id or chain.root_node_id,
            metadata=metadata or {},
        )

        # Link to parent
        if node.parent_node_id and node.parent_node_id in chain.nodes:
            parent = chain.nodes[node.parent_node_id]
            if node.node_id not in parent.children_ids:
                parent.children_ids.append(node.node_id)

        chain.nodes[node.node_id] = node
        return node

    async def complete_and_save_trace(self, task_id: str) -> dict[str, Any] | None:
        """Complete the trace chain and persist to memory."""
        chain = self._active_traces.get(task_id)
        if chain is None:
            return None

        key = chain.trace_id
        data = chain.model_dump(mode="json")

        await memory_orchestrator.write_episodic(chain.user_id, key, data)

        # Audit log
        await self._audit_memory_op(
            user_id=chain.user_id,
            session_id="",
            task_id=task_id,
            operation="trace_save",
            target_id=key,
            details={"node_count": len(chain.nodes)},
        )

        self._active_traces.pop(task_id, None)
        logger.info("Trace chain saved: trace_id=%s, nodes=%d", key, len(chain.nodes))
        return data

    async def load_trace(self, user_id: str, trace_id: str) -> TraceChain | None:
        """Load a trace chain from memory."""
        data = await memory_orchestrator.read_episodic(user_id, trace_id)
        if data is None:
            return None
        try:
            return TraceChain(**data)
        except Exception as e:
            logger.warning("Failed to deserialize trace chain %s: %s", trace_id, e)
            return None

    async def trace_back_from_output(self, user_id: str,
                                      task_id: str) -> list[dict[str, Any]]:
        """Trace back from the final output to every decision step.

        Returns a list of trace nodes from output back to root.
        """
        # Search for trace chains related to this task
        from app.models.memory import MemoryQuery

        query = MemoryQuery(
            memory_type=MemoryType.EPISODIC,
            key_prefix="tr_",
            limit=5,
        )

        records = await memory_orchestrator.search(user_id, MemoryType.EPISODIC, query)

        for record in records:
            try:
                chain = TraceChain(**record.data)
                if chain.task_id == task_id:
                    return self._build_traceback(chain)
            except Exception:
                continue

        return []

    def _build_traceback(self, chain: TraceChain) -> list[dict[str, Any]]:
        """Build a traceback path from leaf nodes back to root."""
        # Find leaf nodes (nodes with no children)
        leaf_nodes = [n for n in chain.nodes.values() if not n.children_ids]

        # BFS from each leaf back to root
        traceback: list[dict[str, Any]] = []
        visited: set[str] = set()

        for leaf in leaf_nodes:
            current = leaf
            path_nodes: list[dict[str, Any]] = []
            while current is not None and current.node_id not in visited:
                visited.add(current.node_id)
                path_nodes.append({
                    "node_id": current.node_id,
                    "node_type": current.node_type,
                    "content": current.content[:200],
                    "timestamp": current.timestamp.isoformat() if current.timestamp else "",
                })
                # Move to parent
                if current.parent_node_id and current.parent_node_id in chain.nodes:
                    current = chain.nodes[current.parent_node_id]
                else:
                    current = None

            traceback.extend(reversed(path_nodes))

        return traceback

    # ------------------------------------------------------------------
    # Audit integration (FR-EM-003)
    # ------------------------------------------------------------------

    async def _audit_memory_op(self, user_id: str, session_id: str,
                                task_id: str, operation: str,
                                target_id: str = "",
                                details: dict[str, Any] | None = None) -> None:
        """Log a memory operation to the audit system.

        S5.7: Fixed event_type naming to match MEMORY_AUDIT_OPS set.
        Operations passed in are already valid event types (e.g., episodic_write,
        trace_save) and should be used directly without 'memory_' prefix.
        """
        try:
            from app.layers.security.audit_logger import audit_logger
            await audit_logger.log(
                event_type=operation,
                user_id=user_id,
                session_id=session_id,
                task_id=task_id,
                details={
                    "target_memory_id": target_id,
                    "memory_type": "episodic",
                    **(details or {}),
                },
                severity="INFO",
            )
        except Exception as e:
            logger.warning("Failed to log audit for memory operation: %s", e)

    # ------------------------------------------------------------------
    # Mapping helpers
    # ------------------------------------------------------------------

    def _path_to_chunk_data(self, path: DecisionPath) -> dict[str, Any]:
        """Convert a DecisionPath to a MemoryChunk-compatible data dict.

        This enables structured retrieval of decision paths as memory chunks.
        """
        # Build a text summary of the decision path
        steps_text: list[str] = []
        for step in path.steps:
            if step.step_type == "input":
                steps_text.append(f"[输入] {step.content[:200]}")
            elif step.step_type == "intent":
                steps_text.append(f"[意图] {step.content}")
            elif step.step_type == "tool_call":
                steps_text.append(f"[工具调用] {step.tool_name}: {step.tool_output[:100]}")
            elif step.step_type == "intermediate":
                steps_text.append(f"[中间结论] {step.content[:200]}")
            elif step.step_type == "output":
                steps_text.append(f"[输出] {step.content[:200]}")

        text = "\n".join(steps_text)

        return {
            "memory_id": f"mem_{path.path_id}",
            "user_id": path.user_id,
            "memory_type": "episodic",
            "category": "decision",
            "content": {
                "text": text,
                "structured": {
                    "path_id": path.path_id,
                    "task_id": path.task_id,
                    "task_type": path.task_type,
                    "session_id": path.session_id,
                    "total_steps": path.total_steps,
                    "tools_used": path.tools_used,
                    "success": path.success,
                    "key_decisions": [
                        s.content for s in path.steps
                        if s.step_type in ("intermediate", "output") and s.content
                    ],
                },
            },
            "metadata": {
                "source": "decision_path",
                "session_id": path.session_id,
                "confidence": 0.9,
                "created_at": path.started_at.isoformat(),
            },
        }


# Global singleton
episodic_memory_manager = EpisodicMemoryManager()
