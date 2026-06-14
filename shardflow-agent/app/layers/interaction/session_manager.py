import time
import uuid
from typing import Any

from app.layers.agent_core.memory_orchestrator import memory_orchestrator
from app.models.memory import MemoryType


class SessionManager:
    """Manages session lifecycle: create, get, update, archive, expire.

    Delegates storage to MemoryOrchestrator (SHORT_TERM memory type)
    so sessions share the same L0+L1 key namespace as the rest of the
    memory system.
    """

    SESSION_TTL: int = 3600

    async def create_session(
        self, user_id: str, task_id: str, session_id: str = ""
    ) -> dict[str, Any]:
        sid = session_id or str(uuid.uuid4())
        now = self._now()
        session = {
            "session_id": sid,
            "user_id": user_id,
            "task_id": task_id,
            "created_at": now,
            "last_active": now,
            "messages": [],
            "state": {"context_usage_ratio": 0.0, "loop_count": 0},
            "context_shard_id": None,
        }
        await memory_orchestrator.write(
            user_id, MemoryType.SHORT_TERM, sid, session, self.SESSION_TTL
        )
        return session

    async def get_session(self, user_id: str, session_id: str) -> dict[str, Any] | None:
        session = await memory_orchestrator.read_session(user_id, session_id)
        if session is None:
            return None
        session["last_active"] = self._now()
        await memory_orchestrator.write(
            user_id, MemoryType.SHORT_TERM, session_id, session, self.SESSION_TTL
        )
        return session

    async def update_session(self, user_id: str, session_id: str, state_updates: dict[str, Any]) -> None:
        session = await self.get_session(user_id, session_id)
        if session is None:
            return
        session["state"].update(state_updates)
        session["last_active"] = self._now()
        await memory_orchestrator.write(
            user_id, MemoryType.SHORT_TERM, session_id, session, self.SESSION_TTL
        )

    async def archive_session(self, user_id: str, session_id: str) -> None:
        await memory_orchestrator.delete_session(user_id, session_id)

    async def cleanup_expired(self) -> int:
        return 0

    def _now(self) -> str:
        return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


session_manager = SessionManager()
