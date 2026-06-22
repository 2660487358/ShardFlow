"""L2 Agent Core: SkillCache — 三级缓存。

Per Skills管理需求规格文档 FR-9 / 实施计划 P5.5.

三级缓存：
- L1 内存缓存：当前会话已加载 Skill 完整定义，会话结束释放
- L2 Redis 缓存：Skill 元数据缓存，TTL 5 分钟，发布新版本主动失效
- L3 MinIO 回源：缓存未命中时从 MinIO 加载完整 Artifact

与 Java 端 SkillRedisConstants 的 Key 规范对齐：
- meta: shardflow:{user_id}:skill:meta:{skill_code}
- index: shardflow:{user_id}:skill:index:{agent_id}
- list: shardflow:{user_id}:skill:list
- categories: shardflow:{user_id}:skill:categories
"""
from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import Any

from app.config import settings
from app.models.skill import SkillMeta

logger = logging.getLogger(__name__)


class SkillCache:
    """三级缓存管理器。

    L1: 进程内字典，会话级（按 session_id 隔离）
    L2: Redis，TTL 5 分钟
    L3: MinIO（由 SkillArtifactLoader 负责）
    """

    L1_TTL: int = 1800  # 30 分钟（会话级）
    L2_TTL: int = 300  # 5 分钟
    L1_MAX_SIZE: int = 100  # 单会话最多缓存 100 个 Skill

    def __init__(self) -> None:
        # L1: session_id -> {skill_code -> (SkillMeta, expire_ts)}
        self._l1: dict[str, dict[str, tuple[SkillMeta, float]]] = {}
        self._lock = asyncio.Lock()

    # ------------------------------------------------------------------
    # 公共接口
    # ------------------------------------------------------------------

    async def get_skill(
        self, session_id: str, user_id: str, skill_code: str
    ) -> SkillMeta | None:
        """获取 Skill 元数据（L1 -> L2 -> L3 回源）。"""
        # L1
        cached = self._l1_get(session_id, skill_code)
        if cached is not None:
            logger.debug(f"SkillCache L1 hit: {skill_code}")
            return cached

        # L2
        cached = await self._l2_get(user_id, skill_code)
        if cached is not None:
            logger.debug(f"SkillCache L2 hit: {skill_code}")
            await self._l1_set(session_id, cached)
            return cached

        # L3 由调用方负责（SkillArtifactLoader.load_artifact）
        logger.debug(f"SkillCache miss: {skill_code}")
        return None

    async def set_skill(
        self, session_id: str, user_id: str, skill: SkillMeta
    ) -> None:
        """写入 Skill 元数据（L1 + L2）。"""
        await self._l1_set(session_id, skill)
        await self._l2_set(user_id, skill)

    async def invalidate(
        self, user_id: str, skill_code: str, session_id: str | None = None
    ) -> None:
        """失效缓存（版本发布/状态变更时调用）。"""
        # L1
        if session_id:
            async with self._lock:
                if session_id in self._l1:
                    self._l1[session_id].pop(skill_code, None)
        else:
            # 失效所有会话的该 Skill
            async with self._lock:
                for sess_cache in self._l1.values():
                    sess_cache.pop(skill_code, None)

        # L2
        await self._l2_delete(user_id, skill_code)

    async def clear_session(self, session_id: str) -> None:
        """清空指定会话的 L1 缓存（会话结束时调用）。"""
        async with self._lock:
            self._l1.pop(session_id, None)

    # ------------------------------------------------------------------
    # L1 内存缓存
    # ------------------------------------------------------------------

    def _l1_get(self, session_id: str, skill_code: str) -> SkillMeta | None:
        sess_cache = self._l1.get(session_id)
        if not sess_cache:
            return None
        entry = sess_cache.get(skill_code)
        if entry is None:
            return None
        skill, expire_ts = entry
        if time.monotonic() > expire_ts:
            sess_cache.pop(skill_code, None)
            return None
        return skill

    async def _l1_set(self, session_id: str, skill: SkillMeta) -> None:
        async with self._lock:
            if session_id not in self._l1:
                self._l1[session_id] = {}
            sess_cache = self._l1[session_id]
            sess_cache[skill.skill_code] = (skill, time.monotonic() + self.L1_TTL)

            # LRU 淘汰
            if len(sess_cache) > self.L1_MAX_SIZE:
                # 淘汰最早过期的
                oldest_code = min(sess_cache, key=lambda k: sess_cache[k][1])
                sess_cache.pop(oldest_code, None)

    # ------------------------------------------------------------------
    # L2 Redis 缓存
    # ------------------------------------------------------------------

    def _l2_key(self, user_id: str, skill_code: str) -> str:
        """与 Java 端 SkillRedisConstants 对齐。"""
        return f"shardflow:{user_id}:skill:meta:{skill_code}"

    async def _l2_get(self, user_id: str, skill_code: str) -> SkillMeta | None:
        try:
            from app.infrastructure.redis_client import redis_client

            r = await redis_client.get_redis()
            raw = await r.get(self._l2_key(user_id, skill_code))
            if raw is None:
                return None
            data = json.loads(raw)
            return self._deserialize_skill(data)
        except Exception as e:
            logger.warning(f"SkillCache L2 get failed: {e}")
            return None

    async def _l2_set(self, user_id: str, skill: SkillMeta) -> None:
        try:
            from app.infrastructure.redis_client import redis_client

            r = await redis_client.get_redis()
            data = self._serialize_skill(skill)
            await r.set(
                self._l2_key(user_id, skill.skill_code),
                json.dumps(data, ensure_ascii=False),
                ex=self.L2_TTL,
            )
        except Exception as e:
            logger.warning(f"SkillCache L2 set failed: {e}")

    async def _l2_delete(self, user_id: str, skill_code: str) -> None:
        try:
            from app.infrastructure.redis_client import redis_client

            r = await redis_client.get_redis()
            await r.delete(self._l2_key(user_id, skill_code))
        except Exception as e:
            logger.warning(f"SkillCache L2 delete failed: {e}")

    # ------------------------------------------------------------------
    # 序列化
    # ------------------------------------------------------------------

    def _serialize_skill(self, skill: SkillMeta) -> dict[str, Any]:
        return {
            "skill_id": skill.skill_id,
            "skill_code": skill.skill_code,
            "skill_name": skill.skill_name,
            "description": skill.description,
            "skill_type": skill.skill_type,
            "trust_tier": skill.trust_tier,
            "owner_id": skill.owner_id,
            "user_id": skill.user_id,
            "current_version": skill.current_version,
            "status": skill.status,
            "trigger_keywords": skill.trigger_keywords,
            "input_schema": skill.input_schema,
            "output_schema": skill.output_schema,
            "cost_estimate": skill.cost_estimate,
            "config": skill.config,
            "tags": skill.tags,
            "category": skill.category,
            "source": skill.source,
            "binding_type": skill.binding_type,
            "priority": skill.priority,
            "config_override": skill.config_override,
            "enabled": skill.enabled,
            "artifacts": skill.artifacts,
            "content_hash": skill.content_hash,
        }

    def _deserialize_skill(self, data: dict[str, Any]) -> SkillMeta:
        return SkillMeta(
            skill_id=int(data.get("skill_id", 0)),
            skill_code=data.get("skill_code", ""),
            skill_name=data.get("skill_name", ""),
            description=data.get("description", ""),
            skill_type=data.get("skill_type", "prompt"),
            trust_tier=data.get("trust_tier", "personal"),
            owner_id=data.get("owner_id", ""),
            user_id=data.get("user_id", ""),
            current_version=data.get("current_version", ""),
            status=data.get("status", "draft"),
            trigger_keywords=data.get("trigger_keywords", []),
            input_schema=data.get("input_schema", {}),
            output_schema=data.get("output_schema", {}),
            cost_estimate=data.get("cost_estimate", {}),
            config=data.get("config", {}),
            tags=data.get("tags", []),
            category=data.get("category", ""),
            source=data.get("source", "CUSTOM"),
            binding_type=data.get("binding_type", "optional"),
            priority=int(data.get("priority", 0)),
            config_override=data.get("config_override", {}),
            enabled=bool(data.get("enabled", True)),
            artifacts=data.get("artifacts", {}),
            content_hash=data.get("content_hash", ""),
        )


# 模块级单例
skill_cache = SkillCache()
