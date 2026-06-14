"""User Profile model for personalized agent behavior.

Per spec section 6.4: Captures user preferences, expertise, and interaction habits
for building and evolving user profiles.
"""
from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, Field


class Preference(BaseModel):
    """User preference data."""
    interests: list[str] = Field(default_factory=list)
    expertise: str = ""                # beginner|intermediate|advanced
    communication_style: str = ""      # concise|detailed|technical
    preferred_sources: dict[str, float] = Field(default_factory=dict)  # source -> weight
    timezone: str = ""


class InteractionHabits(BaseModel):
    """User interaction habit data."""
    common_tasks: list[str] = Field(default_factory=list)
    preferred_depth: str = ""          # surface|architecture_level|deep_dive
    feedback_patterns: str = ""        # frequent_positive|selective|minimal


class UserProfile(BaseModel):
    """User profile per spec section 6.4.

    Accumulated user preferences and interaction habits for personalized behavior.
    """
    profile_id: str = ""
    user_id: str = ""
    profile_version: int = 1
    preference: Preference = Field(default_factory=Preference)
    interaction_habits: InteractionHabits = Field(default_factory=InteractionHabits)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    model_config = {"extra": "allow"}
