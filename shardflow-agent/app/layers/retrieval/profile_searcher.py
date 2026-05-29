"""L3 Retrieval Layer: ProfileSearcher — 用户画像检索。

从 Java kb-profile API 检索用户偏好、历史行为、专业领域信息。
支持 L0 本地缓存 + L1 Redis 缓存，API 不可用时优雅降级。
"""
import json
import logging
from typing import Any

import httpx

from app.config import settings
from app.infrastructure.l0_cache import L0Cache
from app.infrastructure.redis_client import redis_client
from app.models.user_profile import UserProfile

logger = logging.getLogger(__name__)


class ProfileSearcher:
    """用户画像检索器 — 三级缓存架构。

    L0: 本地内存缓存（最快，进程内）
    L1: Redis 缓存（跨进程，TTL 60min）
    L2: Java kb-profile API（最慢，HTTP 调用）
    """

    PROFILE_CACHE_TTL: int = 3600  # 60 minutes

    def __init__(self) -> None:
        self._l0_cache: L0Cache = L0Cache(max_size=128)

    def _cache_key(self, user_id: str) -> str:
        return f"profile:{user_id}"

    def _redis_key(self, user_id: str) -> str:
        return f"shardflow:{user_id}:profile:latest"

    async def search_preferences(self, user_id: str) -> dict[str, Any]:
        """检索用户偏好设置。"""
        profile = await self._get_profile(user_id)
        if profile:
            return profile.preferences.model_dump()
        return {}

    async def search_expertise(self, user_id: str) -> dict[str, Any]:
        """检索用户专业领域信息。"""
        profile = await self._get_profile(user_id)
        if profile:
            return profile.expertise.model_dump()
        return {}

    async def search_habits(self, user_id: str) -> dict[str, Any]:
        """检索用户交互习惯。"""
        profile = await self._get_profile(user_id)
        if profile:
            return profile.habits.model_dump()
        return {}

    async def get_full_profile(self, user_id: str) -> UserProfile | None:
        """获取完整用户画像。"""
        return await self._get_profile(user_id)

    async def _get_profile(self, user_id: str) -> UserProfile | None:
        """三级缓存读取画像。"""
        cache_key = self._cache_key(user_id)

        # L0: 本地缓存
        cached = self._l0_cache.get(cache_key)
        if cached is not None:
            return cached if isinstance(cached, UserProfile) else UserProfile(**cached)

        # L1: Redis 缓存
        try:
            r = await redis_client.get_redis()
            raw = await r.get(self._redis_key(user_id))
            if raw:
                data: dict[str, Any] = json.loads(raw)
                profile = UserProfile(**data)
                self._l0_cache.set(cache_key, profile)
                return profile
        except Exception as e:
            logger.debug(f"Redis profile cache miss for {user_id}: {e}")

        # L2: Java kb-profile API
        try:
            profile = await self._fetch_from_api(user_id)
            if profile:
                self._l0_cache.set(cache_key, profile)
                try:
                    r = await redis_client.get_redis()
                    await r.set(
                        self._redis_key(user_id),
                        json.dumps(profile.model_dump()),
                        ex=self.PROFILE_CACHE_TTL,
                    )
                except Exception:
                    pass
                return profile
        except Exception as e:
            logger.warning(f"Failed to fetch profile for {user_id}: {e}")

        return None

    async def _fetch_from_api(self, user_id: str) -> UserProfile | None:
        """从 Java kb-profile API 获取画像。"""
        base_url = settings.java_base_url
        api_key = settings.java_api_key or settings.llm_api_key
        try:
            async with httpx.AsyncClient(
                base_url=base_url,
                timeout=httpx.Timeout(10.0),
                headers={"X-API-Key": api_key, "Content-Type": "application/json"},
            ) as client:
                resp = await client.get(f"/api/v1/profile/{user_id}")
                if resp.status_code == 404:
                    return None
                resp.raise_for_status()
                data = resp.json()
                return UserProfile(**data)
        except Exception as e:
            logger.warning(f"Java profile API unavailable for {user_id}: {e}")
            return None

    async def invalidate_cache(self, user_id: str) -> None:
        """使缓存失效（画像更新后调用）。"""
        self._l0_cache.invalidate(self._cache_key(user_id))
        try:
            r = await redis_client.get_redis()
            await r.delete(self._redis_key(user_id))
        except Exception:
            pass


profile_searcher = ProfileSearcher()
