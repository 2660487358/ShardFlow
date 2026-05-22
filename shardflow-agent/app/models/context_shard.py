from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class PreferredDepth(str, Enum):
    """通用分析深度（替代代码探索专用 ExplorationDepth）。"""
    OVERVIEW = "OVERVIEW"      # 概览级别
    DETAIL = "DETAIL"          # 详细级别
    DEEP_DIVE = "DEEP_DIVE"    # 深入级别


# 向后兼容别名
ExplorationDepth = PreferredDepth


class KeyDecision(BaseModel):
    decision: str
    reason: str
    confidence: float


class ContextShard(BaseModel):
    """通用 ContextShard 模型 — 支持代码探索、研究、写作、日程等多元任务。

    四大结构：
    - knowledge_state: 已确认/已排除/待探索/关键决策
    - user_context: 用户偏好与画像设置
    - execution_state: 执行进度与工具使用
    - source_preference: 信息来源权重
    """
    # --- 基础标识 ---
    task_id: str
    user_id: str
    session_seq: int

    # --- 任务元信息（新增通用字段） ---
    task_type: str = "general_qa"
    task_goal: str = ""

    # --- knowledge_state: 知识状态 ---
    confirmed: list[dict[str, Any]] = []
    excluded: list[dict[str, Any]] = []
    pending: list[str] = []
    key_decisions: list[KeyDecision] = []

    # --- user_context: 用户画像快照 ---
    user_context: dict[str, Any] = Field(default_factory=lambda: {
        "expertise_level": "intermediate",
        "preferred_depth": "DETAIL",
        "communication_style": "concise",
    })

    # --- execution_state: 执行状态 ---
    execution_state: dict[str, Any] = Field(default_factory=lambda: {
        "completed_steps": [],
        "current_step": "",
        "tools_used": [],
        "progress_pct": 0.0,
    })

    # --- 来源偏好 ---
    source_preference: dict[str, float] = {}

    # --- 分析深度（向后兼容，映射到 user_context.preferred_depth） ---
    exploration_depth: PreferredDepth = PreferredDepth.DETAIL

    # --- 版本控制 ---
    version: int = 1
    status: str = "SHARDED"
