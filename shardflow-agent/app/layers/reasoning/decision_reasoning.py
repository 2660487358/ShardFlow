"""L4 Decision Reasoning Layer: TaskPlanner, PlanExecutor, ConfidenceScorer."""
import re
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
            # ---- 通用模板 ----
            "research": [
                {"id": "s1", "description": "明确调研目标和范围", "depends_on": [], "priority": 1},
                {"id": "s2", "description": "收集相关信息和资料", "depends_on": ["s1"], "priority": 1},
                {"id": "s3", "description": "对比分析不同方案", "depends_on": ["s2"], "priority": 2},
                {"id": "s4", "description": "得出结论和建议", "depends_on": ["s3"], "priority": 2},
            ],
            "writing": [
                {"id": "s1", "description": "确定文档结构和大纲", "depends_on": [], "priority": 1},
                {"id": "s2", "description": "收集和整理素材", "depends_on": ["s1"], "priority": 1},
                {"id": "s3", "description": "撰写内容初稿", "depends_on": ["s2"], "priority": 2},
                {"id": "s4", "description": "校对和润色", "depends_on": ["s3"], "priority": 2},
            ],
            "scheduling": [
                {"id": "s1", "description": "确认时间和参与人", "depends_on": [], "priority": 1},
                {"id": "s2", "description": "检查时间冲突", "depends_on": ["s1"], "priority": 1},
                {"id": "s3", "description": "安排日程或发送邀请", "depends_on": ["s2"], "priority": 2},
            ],
            "planning": [
                {"id": "s1", "description": "分析需求和约束条件", "depends_on": [], "priority": 1},
                {"id": "s2", "description": "制定分步执行计划", "depends_on": ["s1"], "priority": 1},
                {"id": "s3", "description": "评估风险和备选方案", "depends_on": ["s2"], "priority": 2},
                {"id": "s4", "description": "输出最终方案和时间线", "depends_on": ["s3"], "priority": 2},
            ],
            "communication": [
                {"id": "s1", "description": "明确沟通目标和受众", "depends_on": [], "priority": 1},
                {"id": "s2", "description": "组织消息内容", "depends_on": ["s1"], "priority": 1},
                {"id": "s3", "description": "发送并确认接收", "depends_on": ["s2"], "priority": 2},
            ],

            # ---- 代码模板（保留） ----
            "analyze": [
                {"id": "s1", "description": "Identify project structure", "depends_on": [], "priority": 1},
                {"id": "s2", "description": "Analyze entry points and startup", "depends_on": ["s1"], "priority": 1},
                {"id": "s3", "description": "Map service call relationships", "depends_on": ["s1"], "priority": 2},
                {"id": "s4", "description": "Analyze data flow and storage", "depends_on": ["s2", "s3"], "priority": 2},
                {"id": "s5", "description": "Summarize patterns and decisions", "depends_on": ["s4"], "priority": 3},
            ],
            "fix": [
                {"id": "s1", "description": "Locate problematic code", "depends_on": [], "priority": 1},
                {"id": "s2", "description": "Analyze root cause and impact", "depends_on": ["s1"], "priority": 1},
                {"id": "s3", "description": "Design fix approach", "depends_on": ["s2"], "priority": 2},
                {"id": "s4", "description": "Verify fix correctness", "depends_on": ["s3"], "priority": 2},
            ],
            "design": [
                {"id": "s1", "description": "Requirements and constraints", "depends_on": [], "priority": 1},
                {"id": "s2", "description": "Technology research", "depends_on": ["s1"], "priority": 1},
                {"id": "s3", "description": "Detailed solution design", "depends_on": ["s2"], "priority": 2},
                {"id": "s4", "description": "Risk assessment", "depends_on": ["s3"], "priority": 2},
            ],
        }

        # 意图 → 关键词映射（支持中英文）
        intent_keywords: dict[str, list[str]] = {
            "research":     ["调研", "研究", "research", "分析", "对比", "选型"],
            "writing":      ["写", "文档", "报告", "纪要", "总结", "write", "doc"],
            "scheduling":   ["日程", "日历", "提醒", "会议", "schedule", "安排"],
            "planning":     ["计划", "规划", "方案", "plan", "task_plan", "步骤"],
            "communication": ["发送", "消息", "通知", "告诉", "send", "message"],
            "analyze":      ["analyze", "explore", "探索", "分析.*链", "梳理"],
            "fix":          ["fix", "修复", "bug", "debug", "报错", "错误"],
            "design":       ["design", "设计", "架构", "重构", "选型"],
        }

        for keyword, kws in intent_keywords.items():
            for kw in kws:
                if re.search(kw, goal, re.IGNORECASE):
                    return [SubTask(**t) for t in patterns[keyword]]

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
