"""Session State Summary model (replaces ContextShard).

Per spec section 6.2: Task-dimension state snapshots for cross-session continuity.
"""
from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, Field


class KeyDecision(BaseModel):
    """A key decision within a session."""
    decision: str
    reason: str = ""
    confidence: float = 0.0


class KnowledgeState(BaseModel):
    """Knowledge state of the task at the point of summary extraction."""
    confirmed: list[str] = Field(default_factory=list)
    excluded: list[str] = Field(default_factory=list)
    pending: list[str] = Field(default_factory=list)
    key_decisions: list[KeyDecision] = Field(default_factory=list)


class UserContext(BaseModel):
    """User context captured in the session."""
    expertise_level: str = ""          # beginner|intermediate|advanced
    preferred_depth: str = ""          # surface|architecture_level|deep_dive
    communication_style: str = ""      # concise|detailed|technical


class ExecutionState(BaseModel):
    """Execution progress state."""
    completed_steps: int = 0
    current_step: str = ""
    tools_used: list[str] = Field(default_factory=list)
    estimated_remaining: str = ""


class SessionStateSummary(BaseModel):
    """Cross-session state snapshot per spec section 6.2.

    Captures the full task state for seamless session continuation.
    """
    summary_id: str = ""               # UUID v7
    user_id: str = ""
    task_id: str = ""
    session_seq: int = 1               # Which session this summary belongs to
    task_type: str = ""                # research|code_analysis|bug_investigation|...
    task_goal: str = ""
    knowledge_state: KnowledgeState = Field(default_factory=KnowledgeState)
    user_context: UserContext = Field(default_factory=UserContext)
    execution_state: ExecutionState = Field(default_factory=ExecutionState)
    source_preference: dict[str, float] = Field(default_factory=dict)
    version: int = 1
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    model_config = {"extra": "allow"}
