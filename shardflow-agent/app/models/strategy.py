from pydantic import BaseModel


class SourceCombo(BaseModel):
    source: str
    weight: float
    reliability: float


class StrategyRecord(BaseModel):
    strategy_id: str
    user_id: str
    task_type: str
    query_pattern: str
    source_combo: list[SourceCombo]
    success_score: float
    cost_ms: int
    embedding: list[float] | None = None
