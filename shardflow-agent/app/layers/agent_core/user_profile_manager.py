"""L2 Agent Core: UserProfileManager — 画像驱动的个性化推理。

三个核心方法：
- load_profile(): 从 Java kb-profile API 加载用户画像（三级缓存）
- inject_profile(): 将画像注入 PromptEngine 模板
- update_profile(): 检测画像变化后回调 Java 更新

架构规则 AR-3: 每次推理前必须注入用户画像。
"""
import logging
from typing import Any

from app.infrastructure.callback_client import callback_client
from app.layers.agent_core.prompt_engine import prompt_engine
from app.layers.retrieval.profile_searcher import profile_searcher
from app.models.user_profile import UserProfile

logger = logging.getLogger(__name__)


class UserProfileManager:
    """用户画像管理器 — 加载、注入、更新画像。"""

    def __init__(self) -> None:
        self._loaded_profiles: dict[str, UserProfile] = {}

    async def load_profile(self, user_id: str) -> UserProfile | None:
        """加载用户画像（三级缓存）。

        返回 None 表示画像不可用，调用方应使用默认画像降级。
        """
        if user_id in self._loaded_profiles:
            return self._loaded_profiles[user_id]

        profile = await profile_searcher.get_full_profile(user_id)
        if profile:
            self._loaded_profiles[user_id] = profile
            logger.info(f"Profile loaded for user={user_id}, level={profile.expertise.level}")
            return profile

        # 降级：创建默认画像
        logger.info(f"No profile found for user={user_id}, using default")
        default_profile = UserProfile(user_id=user_id)
        self._loaded_profiles[user_id] = default_profile
        return default_profile

    def inject_profile(self, profile: UserProfile | None, state: dict[str, Any]) -> str:
        """将用户画像注入 Prompt 模板。

        返回注入后的 profile_context 文本，同时更新 state 中的相关字段。
        """
        if profile is None:
            profile_context = "暂无用户画像（使用默认设置）"
            state["profile_context"] = profile_context
            state["user_context"] = {
                "expertise_level": "intermediate",
                "preferred_depth": "DETAIL",
                "communication_style": "concise",
            }
            return profile_context

        inject_dict = profile.to_inject_dict()
        profile_context = prompt_engine.build_profile_inject_prompt(inject_dict)
        state["profile_context"] = profile_context
        state["user_context"] = inject_dict
        state["preferred_depth"] = inject_dict.get("preferred_depth", "DETAIL")
        return profile_context

    async def update_profile(self, user_id: str, updates: dict[str, Any]) -> bool:
        """更新用户画像并回调 Java 端。

        Args:
            user_id: 用户 ID
            updates: 要更新的字段（preferences/expertise/habits 的部分更新）

        Returns:
            是否更新成功
        """
        profile = self._loaded_profiles.get(user_id)
        if profile is None:
            profile = UserProfile(user_id=user_id)

        # 合并更新
        if "preferences" in updates:
            for k, v in updates["preferences"].items():
                if hasattr(profile.preferences, k):
                    setattr(profile.preferences, k, v)
        if "expertise" in updates:
            for k, v in updates["expertise"].items():
                if hasattr(profile.expertise, k):
                    setattr(profile.expertise, k, v)
        if "habits" in updates:
            for k, v in updates["habits"].items():
                if hasattr(profile.habits, k):
                    setattr(profile.habits, k, v)

        self._loaded_profiles[user_id] = profile

        # 回调 Java 端
        try:
            await callback_client.update_profile(user_id, updates)
            # 使缓存失效
            await profile_searcher.invalidate_cache(user_id)
            logger.info(f"Profile updated for user={user_id}")
            return True
        except Exception as e:
            logger.warning(f"Failed to update profile for user={user_id}: {e}")
            return False

    def get_loaded_profile(self, user_id: str) -> UserProfile | None:
        """获取已加载的画像（不从 API 重新加载）。"""
        return self._loaded_profiles.get(user_id)

    def clear_profile(self, user_id: str) -> None:
        """清除已缓存的画像。"""
        self._loaded_profiles.pop(user_id, None)


user_profile_manager = UserProfileManager()
