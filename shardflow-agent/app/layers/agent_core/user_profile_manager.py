"""UserProfileManager — 用户画像管理器 (FR-SM-002, FR-SM-003).

Manages user profile lifecycle:
- FR-SM-002: Profile construction and evolution from semantic memory
- FR-SM-003: Profile-based personalization (load + inject into LLM Prompt)
- FR-SM-002: User-initiated profile management (view/edit)

Per Agent架构规则文档:
- load_profile(): Load user profile from L0 → L1 → L2 degrade chain
- inject_profile(): Prepend profile context to LLM Prompt
- update_profile(): Update profile from semantic memory or user input

Redis Key: shardflow:{user_id}:profile:latest (TTL 60min)
"""
import logging
from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, Field

from app.infrastructure.memory_metrics import memory_metrics
from app.layers.agent_core.memory_orchestrator import memory_orchestrator
from app.layers.agent_core.semantic_memory_manager import semantic_memory_manager
from app.models.memory import MemoryType
from app.models.user_profile import InteractionHabits, Preference, UserProfile

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Profile injection format (per spec FR-SM-003)
# ---------------------------------------------------------------------------

PROFILE_INJECTION_TEMPLATE = (
    "[用户画像] 基于历史交互积累的用户偏好：\n"
    "- 专业水平：{expertise}\n"
    "- 沟通风格：{communication_style}\n"
    "- 深度偏好：{preferred_depth}\n"
    "- 常见任务：{common_tasks}\n"
    "- 信息源偏好：{preferred_sources}\n"
    "- 兴趣领域：{interests}\n"
    "- 时区：{timezone}\n\n"
    "请根据以上画像调整回答的深度、风格和信息源选择。"
)


# ---------------------------------------------------------------------------
# UserProfileManager
# ---------------------------------------------------------------------------

class UserProfileManager:
    """Manages user profile: construction, evolution, personalization, and
    user-initiated management.

    Profile data flows:
    - Build: SemanticMemory facts → aggregate into UserProfile
    - Cache: UserProfile → L0 (local) + L1 (Redis) + L2 (Java/PostgreSQL)
    - Apply: UserProfile → inject into LLM Prompt for personalization
    """

    # Redis key pattern per Agent架构规则文档
    REDIS_KEY_PATTERN = "shardflow:{user_id}:profile:latest"
    REDIS_TTL_SECONDS = 3600  # 60 minutes

    # L0 cache: user_id -> UserProfile
    _l0_cache: dict[str, UserProfile] = {}

    def __init__(self) -> None:
        self._l0_cache: dict[str, UserProfile] = {}

    # ------------------------------------------------------------------
    # P7.3.4: Profile completeness tracking
    # ------------------------------------------------------------------

    def _record_profile_completeness(self, user_id: str, profile: UserProfile) -> None:
        """Record profile field completeness to metrics.

        Counts non-empty fields across Preference and InteractionHabits.
        """
        total_fields = 0
        filled_fields = 0

        # Preference fields
        pref = profile.preference
        for field_name in ("expertise", "communication_style", "timezone"):
            total_fields += 1
            if getattr(pref, field_name, ""):
                filled_fields += 1

        # List/dict fields: count as filled if non-empty
        total_fields += 1
        if pref.interests:
            filled_fields += 1
        total_fields += 1
        if pref.preferred_sources:
            filled_fields += 1

        # InteractionHabits fields
        habits = profile.interaction_habits
        for field_name in ("preferred_depth", "feedback_patterns"):
            total_fields += 1
            if getattr(habits, field_name, ""):
                filled_fields += 1

        total_fields += 1
        if habits.common_tasks:
            filled_fields += 1

        memory_metrics.record_profile_completeness(user_id, total_fields, filled_fields)

    # ------------------------------------------------------------------
    # FR-SM-002: Profile construction and evolution
    # ------------------------------------------------------------------

    async def build_profile(self, user_id: str) -> UserProfile:
        """Build or rebuild user profile from semantic memory facts.

        Aggregates all retrievable semantic facts into a structured profile.
        Called when:
        - New semantic facts are extracted
        - Profile is explicitly refreshed
        - Cache miss on load
        """
        # Get all retrievable facts for this user
        facts = await semantic_memory_manager.get_user_facts(user_id, min_confidence=0.7)

        # Load existing profile as base (if any)
        existing = await self._load_from_store(user_id)

        if existing is None:
            existing = UserProfile(
                user_id=user_id,
                created_at=datetime.now(timezone.utc),
            )

        # Aggregate facts into profile fields
        preference = self._aggregate_preference(facts, existing.preference)
        interaction_habits = self._aggregate_interaction_habits(facts, existing.interaction_habits)

        # Update profile
        existing.preference = preference
        existing.interaction_habits = interaction_habits
        existing.profile_version += 1
        existing.updated_at = datetime.now(timezone.utc)

        # Persist to all tiers
        await self._persist_profile(user_id, existing)

        # Record profile completeness metrics
        self._record_profile_completeness(user_id, existing)

        logger.info(
            "Built profile for user %s: version=%d, interests=%d, expertise=%s",
            user_id, existing.profile_version, len(existing.preference.interests),
            existing.preference.expertise,
        )

        return existing

    def _aggregate_preference(
        self,
        facts: list[dict[str, Any]],
        existing: Preference,
    ) -> Preference:
        """Aggregate semantic facts into Preference fields."""
        interests = list(existing.interests)
        expertise = existing.expertise
        communication_style = existing.communication_style
        preferred_sources = dict(existing.preferred_sources)
        timezone = existing.timezone

        for fact in facts:
            category = fact.get("category", "")
            structured = fact.get("structured", {})
            text = fact.get("text", "")
            confidence = fact.get("confidence", 0.7)

            if category == "profile":
                # Extract expertise level
                if "expertise" in structured:
                    expertise = structured["expertise"]
                elif "专业水平" in text:
                    # Parse from text like "用户专业水平: advanced"
                    for level in ["advanced", "intermediate", "beginner"]:
                        if level in text.lower():
                            expertise = level
                            break

            elif category == "preference":
                # Extract communication style
                if "communication_style" in structured:
                    communication_style = structured["communication_style"]
                elif "沟通风格" in text:
                    for style in ["concise", "detailed", "technical"]:
                        if style in text.lower():
                            communication_style = style
                            break

                # Extract interests
                if "interest" in text.lower() or "兴趣" in text:
                    # Add as interest if not already present
                    interest_text = text.replace("用户兴趣", "").replace("兴趣", "").strip("：: ")
                    if interest_text and interest_text not in interests:
                        interests.append(interest_text)

                # Extract source preferences
                if "信息源" in text or "source" in text.lower():
                    if "preferred_sources" in structured:
                        for src, weight in structured["preferred_sources"].items():
                            preferred_sources[src] = max(
                                preferred_sources.get(src, 0), float(weight)
                            )

                # Extract timezone
                if "时区" in text or "timezone" in text.lower():
                    if "timezone" in structured:
                        timezone = structured["timezone"]

                # Extract frequent tool usage as interest
                if "frequent_tool" in structured:
                    tool = structured["frequent_tool"]
                    tool_label = f"常用工具:{tool}"
                    if tool_label not in interests:
                        interests.append(tool_label)

        return Preference(
            interests=interests,
            expertise=expertise,
            communication_style=communication_style,
            preferred_sources=preferred_sources,
            timezone=timezone,
        )

    def _aggregate_interaction_habits(
        self,
        facts: list[dict[str, Any]],
        existing: InteractionHabits,
    ) -> InteractionHabits:
        """Aggregate semantic facts into InteractionHabits fields."""
        common_tasks = list(existing.common_tasks)
        preferred_depth = existing.preferred_depth
        feedback_patterns = existing.feedback_patterns

        for fact in facts:
            structured = fact.get("structured", {})
            text = fact.get("text", "")

            # Extract preferred depth
            if "preferred_depth" in structured:
                preferred_depth = structured["preferred_depth"]
            elif "深度" in text:
                for depth in ["architecture_level", "deep_dive", "surface"]:
                    if depth in text.lower():
                        preferred_depth = depth
                        break

            # Extract common tasks
            if "common_tasks" in structured:
                for task in structured["common_tasks"]:
                    if task not in common_tasks:
                        common_tasks.append(task)

            # Extract frequent tool as task indicator
            if "frequent_tool" in structured:
                task_map = {
                    "web_search": "technology_research",
                    "code_analysis": "code_analysis",
                    "document_read": "document_review",
                }
                task = task_map.get(structured["frequent_tool"])
                if task and task not in common_tasks:
                    common_tasks.append(task)

        return InteractionHabits(
            common_tasks=common_tasks,
            preferred_depth=preferred_depth,
            feedback_patterns=feedback_patterns,
        )

    # ------------------------------------------------------------------
    # FR-SM-002 / FR-SM-003: Load profile (L0 → L1 → L2)
    # ------------------------------------------------------------------

    async def load_profile(self, user_id: str) -> UserProfile | None:
        """Load user profile through L0 → L1 → L2 degrade chain.

        Per Agent架构规则文档:
        - L0 本地缓存 < 1ms
        - L1 Redis < 5ms
        - L2 Java API proxy

        If no profile exists, returns None (caller may trigger build_profile).
        """
        # L0: Local cache
        if user_id in self._l0_cache:
            logger.debug("Profile L0 hit for user %s", user_id)
            return self._l0_cache[user_id]

        # L1 + L2: Load through memory orchestrator
        profile = await self._load_from_store(user_id)

        if profile is not None:
            # Populate L0 cache
            self._l0_cache[user_id] = profile
            logger.debug("Profile loaded from store for user %s", user_id)

        return profile

    async def _load_from_store(self, user_id: str) -> UserProfile | None:
        """Load profile from L1/L2 through memory orchestrator."""
        try:
            data = await memory_orchestrator.read_semantic(user_id, "__profile__")
            if data is None:
                return None

            # Reconstruct UserProfile from stored data
            pref_data = data.get("preference", {})
            habits_data = data.get("interaction_habits", {})

            return UserProfile(
                profile_id=str(data.get("profile_id", "")),
                user_id=user_id,
                profile_version=data.get("profile_version", 1),
                preference=Preference(**pref_data) if pref_data else Preference(),
                interaction_habits=InteractionHabits(**habits_data) if habits_data else InteractionHabits(),
                created_at=data.get("created_at", datetime.now(timezone.utc)),
                updated_at=data.get("updated_at", datetime.now(timezone.utc)),
            )
        except Exception as e:
            logger.warning("Failed to load profile from store for user %s: %s", user_id, e)
            return None

    # ------------------------------------------------------------------
    # FR-SM-003: Profile personalization injection
    # ------------------------------------------------------------------

    async def inject_profile(self, user_id: str) -> str:
        """Generate profile injection text for LLM Prompt.

        Per spec FR-SM-003:
        - New session startup: auto-load user profile
        - Adjust answer depth, style, information source based on profile
        - Recommend relevant historical strategies based on profile

        Returns formatted injection text to prepend to LLM Prompt.
        Returns empty string if no profile exists.
        """
        profile = await self.load_profile(user_id)

        if profile is None:
            # Try to build profile from semantic memory
            profile = await self.build_profile(user_id)

        if profile is None or (not profile.preference.expertise and not profile.preference.interests):
            logger.debug("No meaningful profile to inject for user %s", user_id)
            return ""

        # Format injection text
        injection = PROFILE_INJECTION_TEMPLATE.format(
            expertise=profile.preference.expertise or "未设定",
            communication_style=profile.preference.communication_style or "未设定",
            preferred_depth=profile.interaction_habits.preferred_depth or "未设定",
            common_tasks=", ".join(profile.interaction_habits.common_tasks) or "未设定",
            preferred_sources=self._format_sources(profile.preference.preferred_sources),
            interests=", ".join(profile.preference.interests) or "未设定",
            timezone=profile.preference.timezone or "未设定",
        )

        logger.info("Injected profile for user %s (version %d)", user_id, profile.profile_version)
        return injection

    def _format_sources(self, sources: dict[str, float]) -> str:
        """Format preferred sources dict as readable string."""
        if not sources:
            return "未设定"
        sorted_sources = sorted(sources.items(), key=lambda x: x[1], reverse=True)
        return ", ".join(f"{src}({weight:.1f})" for src, weight in sorted_sources[:5])

    # ------------------------------------------------------------------
    # FR-SM-002: User-initiated profile management
    # ------------------------------------------------------------------

    async def get_profile(self, user_id: str) -> UserProfile | None:
        """Get user profile for display/editing (user-initiated).

        Returns the current profile or None if no profile exists.
        """
        return await self.load_profile(user_id)

    async def update_profile(
        self,
        user_id: str,
        preference: dict[str, Any] | None = None,
        interaction_habits: dict[str, Any] | None = None,
    ) -> UserProfile:
        """Update user profile with user-provided data.

        Merges user-provided fields into the existing profile.
        This is for explicit user edits (FR-SM-002: user can view and modify).
        """
        profile = await self.load_profile(user_id)

        if profile is None:
            profile = UserProfile(
                user_id=user_id,
                created_at=datetime.now(timezone.utc),
            )

        # Merge preference updates
        if preference:
            current_pref = profile.preference.model_dump()
            current_pref.update(preference)
            profile.preference = Preference(**current_pref)

        # Merge interaction habits updates
        if interaction_habits:
            current_habits = profile.interaction_habits.model_dump()
            current_habits.update(interaction_habits)
            profile.interaction_habits = InteractionHabits(**current_habits)

        profile.profile_version += 1
        profile.updated_at = datetime.now(timezone.utc)

        # Persist to all tiers
        await self._persist_profile(user_id, profile)

        # Record profile completeness metrics
        self._record_profile_completeness(user_id, profile)

        logger.info(
            "User updated profile for %s: version=%d",
            user_id, profile.profile_version,
        )

        return profile

    async def delete_profile(self, user_id: str) -> bool:
        """Delete user profile (user-initiated, per 被遗忘权).

        Removes from L0, L1, L2.
        """
        # Remove from L0
        self._l0_cache.pop(user_id, None)

        # Remove from L1/L2
        try:
            await memory_orchestrator.delete(user_id, MemoryType.SEMANTIC, "__profile__")
            logger.info("Deleted profile for user %s", user_id)
            return True
        except Exception as e:
            logger.warning("Failed to delete profile for user %s: %s", user_id, e)
            return False

    # ------------------------------------------------------------------
    # Persistence helpers
    # ------------------------------------------------------------------

    async def _persist_profile(self, user_id: str, profile: UserProfile) -> None:
        """Persist profile to L0 + L1 + L2."""
        # L0: Update local cache
        self._l0_cache[user_id] = profile

        # L1 + L2: Persist through memory orchestrator
        profile_data = {
            "profile_id": profile.profile_id,
            "user_id": profile.user_id,
            "profile_version": profile.profile_version,
            "preference": profile.preference.model_dump(),
            "interaction_habits": profile.interaction_habits.model_dump(),
            "created_at": profile.created_at.isoformat() if isinstance(profile.created_at, datetime) else str(profile.created_at),
            "updated_at": profile.updated_at.isoformat() if isinstance(profile.updated_at, datetime) else str(profile.updated_at),
        }

        try:
            await memory_orchestrator.write_semantic(user_id, "__profile__", profile_data)
            logger.debug("Persisted profile for user %s (version %d)", user_id, profile.profile_version)
        except Exception as e:
            logger.warning("Failed to persist profile for user %s: %s", user_id, e)

    # ------------------------------------------------------------------
    # Profile evolution: auto-update from new semantic facts
    # ------------------------------------------------------------------

    async def evolve_profile(self, user_id: str,
                             patch: dict[str, Any] | None = None) -> UserProfile | None:
        """Evolve user profile by incorporating new semantic facts.

        S5.2: Fixed signature to accept patch parameter from
        SemanticMemoryManager.apply_profile_patch().

        Called after semantic extraction to update the profile with new facts.
        If a patch is provided, applies the patch incrementally; otherwise
        rebuilds the profile from all semantic facts.

        Args:
            user_id: User identifier
            patch: Optional profile patch from generate_profile_patch().
                   When provided, applies incremental updates from the patch
                   instead of full rebuild.

        Returns:
            Updated UserProfile, or None if update failed.
        """
        profile = await self.load_profile(user_id)
        if profile is None:
            # No existing profile, build from scratch
            return await self.build_profile(user_id)

        if patch is not None:
            # S5.2: Apply incremental patch instead of full rebuild
            return await self._apply_patch(user_id, profile, patch)

        # No patch provided, rebuild from all facts
        return await self.build_profile(user_id)

    async def _apply_patch(self, user_id: str, profile: UserProfile,
                           patch: dict[str, Any]) -> UserProfile:
        """S5.2: Apply a semantic patch to the profile incrementally.

        Merges patch fields (expertise_level, communication_style, preferences,
        profile_attributes, frequent_tools) into the existing profile without
        full rebuild.
        """
        pref = profile.preference
        habits = profile.interaction_habits

        # Apply expertise level
        expertise = patch.get("expertise_level", "")
        if expertise and not pref.expertise:
            pref.expertise = expertise
        elif expertise and pref.expertise:
            # Only update if patch has higher confidence (explicit confirmation)
            pref.expertise = expertise

        # Apply communication style
        comm_style = patch.get("communication_style", "")
        if comm_style and not pref.communication_style:
            pref.communication_style = comm_style
        elif comm_style and pref.communication_style:
            pref.communication_style = comm_style

        # Apply preferences as interests
        for pref_item in patch.get("preferences", []):
            value = pref_item.get("value", "")
            if value and value not in pref.interests:
                pref.interests.append(value)

        # Apply profile attributes
        for attr_item in patch.get("profile_attributes", []):
            value = attr_item.get("value", "")
            if value and value not in pref.interests:
                pref.interests.append(value)

        # Apply frequent tools as interests and common tasks
        for tool in patch.get("frequent_tools", []):
            tool_label = f"常用工具:{tool}"
            if tool_label not in pref.interests:
                pref.interests.append(tool_label)

            # Map tool to common task
            task_map = {
                "web_search": "technology_research",
                "code_analysis": "code_analysis",
                "document_read": "document_review",
            }
            task = task_map.get(tool)
            if task and task not in habits.common_tasks:
                habits.common_tasks.append(task)

        # Increment version and update timestamp
        profile.profile_version += 1
        profile.updated_at = datetime.now(timezone.utc)

        # Persist to all tiers
        await self._persist_profile(user_id, profile)

        # Record profile completeness metrics
        self._record_profile_completeness(user_id, profile)

        logger.info(
            "S5.2: Applied profile patch for user %s: version=%d, patch_facts=%d",
            user_id, profile.profile_version, patch.get("fact_count", 0),
        )

        return profile

    # ------------------------------------------------------------------
    # Cache management
    # ------------------------------------------------------------------

    def invalidate_cache(self, user_id: str) -> None:
        """Invalidate L0 cache for a user (e.g., after external update)."""
        self._l0_cache.pop(user_id, None)
        logger.debug("Invalidated L0 profile cache for user %s", user_id)

    def get_cache_stats(self) -> dict[str, int]:
        """Get L0 cache statistics."""
        return {
            "cached_profiles": len(self._l0_cache),
        }


# Global singleton
user_profile_manager = UserProfileManager()
