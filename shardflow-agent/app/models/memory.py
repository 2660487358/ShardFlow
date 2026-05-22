"""Memory type system for the Memory Interface Layer (L2 Agent Core).

Defines the three memory categories per AGENT_LAYER_MODEL.md:
- SHORT_TERM: Session context, sliding window messages, ephemeral conversation state
- LONG_TERM:  ContextShard state packages that persist across sessions
- META:      Strategy records, source preferences, learned patterns

Also defines MemoryRecord (the unit of storage) and MemoryQuery (search parameters).
"""
from datetime import datetime, timezone
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class MemoryType(str, Enum):
    """Three-tier memory classification per the six-layer architecture."""
    SHORT_TERM = "short_term"   # Session-scoped: messages, window, pending
    LONG_TERM = "long_term"     # Cross-session: ContextShard state packages
    META = "meta"               # Learned: StrategyRecord, source preferences


class MemoryRecord(BaseModel):
    """A single memory entry stored/retrieved through the MemoryStore interface.

    This is the canonical in-memory representation. Adapters serialize/deserialize
    to their respective backend formats.
    """
    key: str                                              # Unique key within user+type namespace
    user_id: str = ""
    memory_type: MemoryType = MemoryType.SHORT_TERM
    data: dict[str, Any] = Field(default_factory=dict)    # Payload
    version: int = 1                                       # Optimistic locking version
    ttl_seconds: int = 0                                   # 0 = no TTL (permanent)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    tags: list[str] = Field(default_factory=list)          # For search/filtering

    model_config = {"extra": "allow"}


class MemoryQuery(BaseModel):
    """Search/filter parameters for memory retrieval."""
    memory_type: MemoryType | None = None
    tags: list[str] = Field(default_factory=list)
    key_prefix: str = ""                                   # Key prefix filter
    created_after: datetime | None = None
    created_before: datetime | None = None
    limit: int = 10
    offset: int = 0

    model_config = {"extra": "allow"}
