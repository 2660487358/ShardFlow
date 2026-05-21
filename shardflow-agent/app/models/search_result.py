from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, Field


class SearchResult(BaseModel):
    source: str
    title: str
    snippet: str
    url: str
    relevance_score: float = 0.0
    metadata: dict[str, Any] = {}
    retrieved_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class ToolMetadata(BaseModel):
    name: str
    description: str
    version: str = "1.0.0"
    input_schema: dict[str, Any] = {}
    output_schema: dict[str, Any] = {}
    permissions: list[str] = []
    timeout_ms: int = 30000
    retry_count: int = 3
