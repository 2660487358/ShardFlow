"""L4 Decision Reasoning Layer: TaskPlanner, PlanExecutor, ConfidenceScorer."""
from typing import Any

from pydantic import BaseModel


class SubTask(BaseModel):
    id: str
    description: str = ""
    depends_on: list[str] = []
    estimated_tokens: int = 1000
    priority: int = 1
    status: str = "pending"

    model_config = {"extra": "allow"}


class TaskPlanner:
    async def decompose_goal(self, goal: str, context: dict[str, Any] | None = None) -> list[SubTask]:
        subtasks = self._heuristic_decompose(goal)
        return subtasks

    def _heuristic_decompose(self, goal: str) -> list[SubTask]:
        patterns: dict[str, list[dict[str, Any]]] = {
            "analyze": [
                {"id": "s1", "description": "Identify project structure", "deps": [], "priority": 1},
                {"id": "s2", "description": "Analyze entry points and startup", "deps": ["s1"], "priority": 1},
                {"id": "s3", "description": "Map service call relationships", "deps": ["s1"], "priority": 2},
                {"id": "s4", "description": "Analyze data flow and storage", "deps": ["s2", "s3"], "priority": 2},
                {"id": "s5", "description": "Summarize patterns and decisions", "deps": ["s4"], "priority": 3},
            ],
            "fix": [
                {"id": "s1", "description": "Locate problematic code", "deps": [], "priority": 1},
                {"id": "s2", "description": "Analyze root cause and impact", "deps": ["s1"], "priority": 1},
                {"id": "s3", "description": "Design fix approach", "deps": ["s2"], "priority": 2},
                {"id": "s4", "description": "Verify fix correctness", "deps": ["s3"], "priority": 2},
            ],
            "design": [
                {"id": "s1", "description": "Requirements and constraints", "deps": [], "priority": 1},
                {"id": "s2", "description": "Technology research", "deps": ["s1"], "priority": 1},
                {"id": "s3", "description": "Detailed solution design", "deps": ["s2"], "priority": 2},
                {"id": "s4", "description": "Risk assessment", "deps": ["s3"], "priority": 2},
            ],
        }

        for keyword, template in patterns.items():
            if keyword in goal:
                return [SubTask(**t) for t in template]

        return [
            SubTask(id="s1", description=f"Analyze: {goal[:60]}", depends_on=[], priority=1),
            SubTask(id="s2", description="Deep dive into key modules", depends_on=["s1"], priority=2),
            SubTask(id="s3", description="Summarize and verify findings", depends_on=["s2"], priority=3),
        ]

    def estimate_effort(self, subtasks: list[SubTask]) -> dict[str, int]:
        return {s.id: s.estimated_tokens for s in subtasks}

    def prioritize(self, subtasks: list[SubTask]) -> list[SubTask]:
        return sorted(subtasks, key=lambda s: (s.priority, len(s.depends_on)))


class PlanExecutor:
    def build_dag(self, subtasks: list[SubTask]) -> dict[str, set[str]]:
        dag: dict[str, set[str]] = {}
        for s in subtasks:
            dag[s.id] = set(s.depends_on)
        return dag

    def get_next_tasks(self, dag: dict[str, set[str]], completed: set[str]) -> list[str]:
        ready: list[str] = []
        for task_id, deps in dag.items():
            if task_id not in completed and deps.issubset(completed):
                ready.append(task_id)
        return ready

    def check_completion(self, dag: dict[str, set[str]], completed: set[str]) -> bool:
        return set(dag.keys()) == completed


class ConfidenceScorer:
    def score_completion(self, state: dict[str, Any]) -> float:
        subtasks_total = state.get("subtasks_total", 1)
        subtasks_done = state.get("subtasks_done", 0)
        pending = state.get("pending", [])
        pending_count = len(pending) if pending else 0

        task_score = subtasks_done / max(subtasks_total, 1)
        pending_score = 1.0 - min(pending_count / 10.0, 1.0)
        usage_score = 1.0 - state.get("context_usage_ratio", 0)

        result: float = float(task_score * 0.4 + pending_score * 0.3 + usage_score * 0.3)
        return round(result, 2)

    def score_individual_fact(self, fact: dict[str, Any]) -> float:
        evidence = fact.get("evidence", [])
        evidence_score = min(len(evidence) / 3.0, 1.0)
        confidence = fact.get("confidence", 0.5)
        result = float(evidence_score * 0.4 + confidence * 0.6)
        return round(result, 2)

    def recommend_continue(self, state: dict[str, Any]) -> bool:
        score = self.score_completion(state)
        return score < 0.7


task_planner = TaskPlanner()
plan_executor = PlanExecutor()
confidence_scorer = ConfidenceScorer()
