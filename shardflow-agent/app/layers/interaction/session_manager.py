import json
import time
import uuid
from typing import Any

from app.infrastructure.redis_client import redis_client


class SessionManager:
    """Manages session lifecycle: create, get, update, archive, expire."""

    SESSION_TTL: int = 1800
    KEY_PREFIX: str = "kb"

    def _session_key(self, tenant_id: str, session_id: str) -> str:
        return f"{self.KEY_PREFIX}:{tenant_id}:session:{session_id}"

    async def create_session(
        self, tenant_id: str, task_id: str, session_id: str = ""
    ) -> dict[str, Any]:
        sid = session_id or str(uuid.uuid4())
        now = self._now()
        session: dict[str, Any] = {
            "session_id": sid,
            "tenant_id": tenant_id,
            "task_id": task_id,
            "created_at": now,
            "last_active": now,
            "messages": [],
            "state": {"context_usage_ratio": 0.0, "loop_count": 0},
            "context_shard_id": None,
        }
        r = await redis_client.get_redis()
        await r.set(self._session_key(tenant_id, sid), json.dumps(session), ex=self.SESSION_TTL)
        return session

    async def get_session(self, tenant_id: str, session_id: str) -> dict[str, Any] | None:
        r = await redis_client.get_redis()
        raw = await r.get(self._session_key(tenant_id, session_id))
        if raw is None:
            return None
        session: dict[str, Any] = json.loads(raw)
        session["last_active"] = self._now()
        await r.set(
            self._session_key(tenant_id, session_id),
            json.dumps(session),
            ex=self.SESSION_TTL,
        )
        return session

    async def update_session(self, tenant_id: str, session_id: str, state_updates: dict[str, Any]) -> None:
        session = await self.get_session(tenant_id, session_id)
        if session is None:
            return
        session["state"].update(state_updates)
        session["last_active"] = self._now()
        r = await redis_client.get_redis()
        await r.set(
            self._session_key(tenant_id, session_id),
            json.dumps(session),
            ex=self.SESSION_TTL,
        )

    async def archive_session(self, tenant_id: str, session_id: str) -> None:
        r = await redis_client.get_redis()
        await r.delete(self._session_key(tenant_id, session_id))

    async def cleanup_expired(self) -> int:
        return 0

    def _now(self) -> str:
        return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


session_manager = SessionManager()
