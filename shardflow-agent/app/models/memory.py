"""Memory type system for the Memory Architecture (Four-layer model).

Defines the four-layer memory classification per 记忆架构需求规格文档:
- SHORT_TERM:      Session-scoped working memory, direct LLM Prompt injection
- SESSION_SUMMARY: Cross-session state snapshots (replaces ContextShard)
- SEMANTIC:        User facts, preferences, profile data
- EPISODIC:        Decision paths, historical events, audit trails

Also defines MemoryRecord (the unit of storage), MemoryQuery (search parameters),
MemoryChunk (atomic memory unit), and MemoryQueryResult (search result).
"""
from datetime import datetime, timezone
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class MemoryType(str, Enum):
    """Four-layer memory classification per the memory architecture spec."""
    SHORT_TERM = "short_term"           # Working memory: current session context
    SESSION_SUMMARY = "session_summary" # Cross-session state snapshots
    SEMANTIC = "semantic"               # User facts, preferences, profile
    EPISODIC = "episodic"               # Decision paths, historical events


class MemoryRecord(BaseModel):
    """A single memory entry stored/retrieved through the memory system.

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


# ---------------------------------------------------------------------------
# Memory Chunk — atomic memory unit (per spec section 6.1)
# ---------------------------------------------------------------------------

class MemoryContent(BaseModel):
    """Content payload of a MemoryChunk."""
    text: str = ""
    embedding: list[float] = Field(default_factory=list)
    structured: dict[str, Any] = Field(default_factory=dict)


class MemoryMetadata(BaseModel):
    """Metadata of a MemoryChunk."""
    source: str = "conversation"  # conversation|explicit_confirmation|ner_extraction|scheduled_task
    session_id: str = ""
    confidence: float = 1.0
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    expires_at: datetime | None = None
    version: int = 1
    access_count: int = 0
    last_accessed_at: datetime | None = None


class ConflictInfo(BaseModel):
    """Conflict detection info for a MemoryChunk."""
    has_conflict: bool = False
    conflict_with: str | None = None       # memory_id of conflicting chunk
    resolution_status: str | None = None    # pending|resolved|escalated


class MemoryChunk(BaseModel):
    """Atomic memory unit per spec section 6.1.

    Represents a single piece of long-term memory (semantic or episodic).
    """
    memory_id: str = ""                     # UUID v7
    user_id: str = ""
    memory_type: MemoryType = MemoryType.SEMANTIC  # semantic | episodic
    category: str = ""                      # preference|profile|history|decision|strategy
    content: MemoryContent = Field(default_factory=MemoryContent)
    metadata: MemoryMetadata = Field(default_factory=MemoryMetadata)
    conflict_info: ConflictInfo = Field(default_factory=ConflictInfo)

    model_config = {"extra": "allow"}


class MemoryQueryResult(BaseModel):
    """A single result from a memory search query."""
    memory_id: str = ""
    content_text: str = ""
    similarity_score: float = 0.0
    confidence: float = 0.0
    category: str = ""
    memory_type: MemoryType = MemoryType.SEMANTIC
    metadata: dict[str, Any] = Field(default_factory=dict)

    model_config = {"extra": "allow"}
