from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, Field


class UserPreferences(BaseModel):
    """用户偏好设置，驱动 Prompt 个性化和工具选择。"""
    communication_style: str = "concise"        # concise/detailed/conversational
    preferred_depth: str = "DETAIL"            # OVERVIEW/DETAIL/DEEP_DIVE
    preferred_sources: dict[str, float] = {}   # source_name -> weight
    language: str = "zh-CN"


class UserExpertise(BaseModel):
    """用户专业领域信息。"""
    level: str = "intermediate"               # beginner/intermediate/expert
    domains: list[str] = []                   # e.g. ["backend", "microservices"]
    tech_stack: list[str] = []                # e.g. ["Java", "Spring", "Redis"]


class UserHabits(BaseModel):
    """用户交互习惯，用于优化体验。"""
    common_task_types: list[str] = []         # e.g. ["research", "code_explore"]
    peak_hours: list[int] = []                # e.g. [9, 10, 14, 15]
    avg_session_duration_min: int = 30
    preferred_tools: list[str] = []           # e.g. ["web_search", "read_file"]


class UserProfile(BaseModel):
    """用户画像完整模型，与 Java 端 kb_user_profile 表结构对齐。"""
    user_id: str
    preferences: UserPreferences = Field(default_factory=UserPreferences)
    expertise: UserExpertise = Field(default_factory=UserExpertise)
    habits: UserHabits = Field(default_factory=UserHabits)
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    def to_inject_dict(self) -> dict[str, Any]:
        """导出为 Prompt 注入用的扁平字典。"""
        return {
            "expertise_level": self.expertise.level,
            "preferred_depth": self.preferences.preferred_depth,
            "communication_style": self.preferences.communication_style,
            "domains": self.expertise.domains,
            "tech_stack": self.expertise.tech_stack,
            "preferred_sources": self.preferences.preferred_sources,
        }
