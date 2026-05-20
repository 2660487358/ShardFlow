from enum import Enum
from typing import Any

from pydantic import BaseModel


class ExplorationDepth(str, Enum):
    SERVICE_LEVEL = "SERVICE_LEVEL"
    METHOD_LEVEL = "METHOD_LEVEL"
    LINE_LEVEL = "LINE_LEVEL"


class KeyDecision(BaseModel):
    decision: str
    reason: str
    confidence: float


class ContextShard(BaseModel):
    task_id: str
    tenant_id: str
    session_seq: int
    confirmed: list[dict[str, Any]]
    excluded: list[dict[str, Any]]
    pending: list[str]
    source_preference: dict[str, float]
    exploration_depth: ExplorationDepth
    key_decisions: list[KeyDecision]
    version: int = 1
    status: str = "SHARDED"
