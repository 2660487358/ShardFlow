import logging
import time
import uuid
from typing import Any

from app.layers.agent_core.memory_orchestrator import memory_orchestrator
from app.models.memory import MemoryType

logger = logging.getLogger(__name__)


class SessionManager:
    """Manages session lifecycle: create, get, update, archive, expire.

    Delegates storage to MemoryOrchestrator (SHORT_TERM memory type)
    so sessions share the same L0+L1 key namespace as the rest of the
    memory system.

    T2.6: SESSION_TTL 调整为 24h，与 WorkingMemory window TTL 对齐，
    避免会话状态提前过期导致历史记忆丢失。
    """

    # 24h — 会话生命周期，与 SESSION_WINDOW_TTL_SECONDS 保持一致
    SESSION_TTL: int = 24 * 3600

    # 即将过期提示阈值（5 分钟）
    EXPIRY_WARNING_THRESHOLD: int = 5 * 60

    def _session_meta_key(self, session_id: str) -> str:
        """Build the memory key for session metadata.

        Uses a dedicated namespace 'session:{session_id}' to avoid colliding
        with WorkingMemory's SHORT_TERM snapshot key.
        """
        return f"session:{session_id}"

    async def create_session(
        self, user_id: str, task_id: str, session_id: str = ""
    ) -> dict[str, Any]:
        sid = session_id or str(uuid.uuid4())
        now = self._now()
        session: dict[str, Any] = {
            "session_id": sid,
            "user_id": user_id,
            "task_id": task_id,
            "created_at": now,
            "last_active": now,
            "messages": [],
            "state": {"context_usage_ratio": 0.0, "loop_count": 0},
            "context_shard_id": None,
            "ttl_seconds": self.SESSION_TTL,
        }
        await memory_orchestrator.write(
            user_id, MemoryType.SHORT_TERM, self._session_meta_key(sid), session, self.SESSION_TTL
        )
        return session

    async def get_session(self, user_id: str, session_id: str) -> dict[str, Any] | None:
        session = await memory_orchestrator.read(
            user_id, MemoryType.SHORT_TERM, self._session_meta_key(session_id)
        )
        if session is None:
            return None
        session_data = session.data
        session_data["last_active"] = self._now()
        await memory_orchestrator.write(
            user_id, MemoryType.SHORT_TERM, self._session_meta_key(session_id), session_data, self.SESSION_TTL
        )
        return session_data

    async def update_session(self, user_id: str, session_id: str, state_updates: dict[str, Any]) -> None:
        session = await self.get_session(user_id, session_id)
        if session is None:
            return
        session["state"].update(state_updates)
        session["last_active"] = self._now()
        await memory_orchestrator.write(
            user_id, MemoryType.SHORT_TERM, self._session_meta_key(session_id), session, self.SESSION_TTL
        )

    async def archive_session(self, user_id: str, session_id: str) -> None:
        """归档 session：触发数据归档（写入 L2 + 提取记忆 + 清理 Redis）。"""
        # 触发 WorkingMemory 归档（提取语义/情景记忆、写入 SESSION_SUMMARY）
        try:
            from app.layers.agent_core.working_memory_manager import working_memory_manager
            archive_result = await working_memory_manager.archive_session(session_id)
            if not archive_result.get("archived"):
                logger.info(
                    "WorkingMemory archive skipped for session=%s: %s",
                    session_id, archive_result.get("reason", ""),
                )
        except Exception as e:
            logger.warning(
                "WorkingMemory archive failed for session=%s: %s", session_id, e,
            )

        # 清理 SHORT_TERM session 元数据记录（与 WorkingMemory 快照 key 分离）
        await memory_orchestrator.delete(
            user_id, MemoryType.SHORT_TERM, self._session_meta_key(session_id)
        )

    async def get_expiry_status(self, user_id: str, session_id: str) -> dict[str, Any]:
        """获取 session 过期状态。

        Returns:
            {
                "expired": bool,
                "expiring_soon": bool,
                "expires_at": str,
                "remaining_seconds": int,
            }
        """
        record = await memory_orchestrator.read(
            user_id, MemoryType.SHORT_TERM, self._session_meta_key(session_id)
        )
        if record is None:
            return {
                "expired": True,
                "expiring_soon": False,
                "expires_at": "",
                "remaining_seconds": 0,
            }

        # Redis TTL 是最准确的过期判断
        try:
            from app.infrastructure.redis_client import redis_client
            r = await redis_client.get_redis()
            from app.layers.agent_core.memory_adapters.redis_adapter import RedisAdapter
            adapter = RedisAdapter()
            redis_key = adapter._build_key(
                user_id, MemoryType.SHORT_TERM, self._session_meta_key(session_id)
            )
            remaining = await r.ttl(redis_key)
        except Exception:
            remaining = -2

        if remaining == -2 or remaining == -1:
            # -2: key 不存在（已过期）；-1: 无 TTL（异常情况）
            return {
                "expired": remaining == -2,
                "expiring_soon": False,
                "expires_at": "",
                "remaining_seconds": 0 if remaining == -2 else self.SESSION_TTL,
            }

        return {
            "expired": remaining <= 0,
            "expiring_soon": 0 < remaining <= self.EXPIRY_WARNING_THRESHOLD,
            "expires_at": time.strftime(
                "%Y-%m-%dT%H:%M:%SZ", time.gmtime(time.time() + remaining)
            ),
            "remaining_seconds": remaining,
        }

    async def cleanup_expired(self) -> int:
        return 0

    def _now(self) -> str:
        return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


session_manager = SessionManager()
