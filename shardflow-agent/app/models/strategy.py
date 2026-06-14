"""Strategy Record model for tool combination tracking and reuse.

Per spec section 6.3: Records tool combos, user feedback, and success scores
for strategy reuse across similar tasks.
"""
from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, Field


class ToolComboItem(BaseModel):
    """A single tool in a strategy's tool combination."""
    tool: str
    weight: float = 0.0
    reliability: float = 0.0


class StrategyRecord(BaseModel):
    """Strategy record per spec section 6.3.

    Captures tool combinations, weights, reliability, user feedback,
    and success scores for future strategy reuse.
    """
    record_id: str = ""                # e.g. "sr-001"
    user_id: str = ""
    task_type: str = ""
    query_pattern: str = ""
    tool_combo: list[ToolComboItem] = Field(default_factory=list)
    user_feedback: dict[str, str] = Field(default_factory=dict)  # tool_name -> "useful"|"not_relevant"
    success_score: float = 0.0
    cost_ms: int = 0
    embedding: list[float] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    model_config = {"extra": "allow"}
