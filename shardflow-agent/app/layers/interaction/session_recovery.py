"""Cross-port session resume and recovery (FR-SS-003).

Refactored to integrate with SessionStateSummaryManager for proper
cross-port session continuation. Previously, inject_shard_on_resume
was a no-op; now it loads the latest summary and injects it into
the resumed session state.
"""
import json
import logging
from typing import Any

from app.infrastructure.redis_client import redis_client
from app.layers.agent_core.session_state_summary_manager import session_state_summary_manager

logger = logging.getLogger(__name__)


class SessionRecoveryManager:
    """Manages cross-port session resume and recovery.

    Integration points:
    - archive_with_shard_check: Archives session and extracts summary
    - try_resume_session: Finds and resumes a session by task_id
    - inject_shard_on_resume: Injects session state summary into resumed session
    """

    async def archive_with_shard_check(
        self, user_id: str, session_id: str, state: dict[str, Any],
    ) -> dict[str, Any]:
        """Archive a session, extract summary, and publish event.

        Enhanced: Now also triggers summary extraction via
        SessionStateSummaryManager before archiving.
        """
        r = await redis_client.get_redis()
        session_key = f"shardflow:{user_id}:session:{session_id}"

        task_id = state.get("task_id", "")

        # Extract and save session state summary before archiving
        if task_id:
            try:
                messages = state.get("messages", [])
                context_summary = state.get("context_summary", "")
                intent_stack = state.get("intent_stack", [])

                await session_state_summary_manager.extract_and_save(
                    user_id=user_id,
                    task_id=task_id,
                    session_seq=state.get("session_seq", 1),
                    task_type=state.get("task_type", ""),
                    task_goal=state.get("task_goal", ""),
                    messages=messages,
                    context_summary=context_summary,
                    intent_stack=intent_stack,
                    trigger="session_end",
                )
                logger.info("Summary extracted during archive for task %s", task_id)
            except Exception as e:
                logger.warning("Failed to extract summary during archive: %s", e)

        # Delete session from Redis
        await r.delete(session_key)

        # Publish archive event
        if task_id:
            await r.publish(f"shardflow:{user_id}:events", json.dumps({
                "event": "session_archived",
                "task_id": task_id,
                "session_id": session_id,
            }))

        return state

    async def try_resume_session(
        self, user_id: str, task_id: str,
    ) -> dict[str, Any] | None:
        """Try to resume a session by finding its data in Redis.

        Enhanced: Falls back to loading from SessionStateSummaryManager
        if no active session is found in Redis.
        """
        r = await redis_client.get_redis()
        prefix = f"shardflow:{user_id}:session:"

        # First, try to find an active session in Redis
        async for key in r.scan_iter(match=f"{prefix}*", count=50):
            raw = await r.get(key)
            if raw:
                data: dict[str, Any] = json.loads(raw)
                if data.get("task_id") == task_id:
                    return data

        # Fallback: Try to resume from session state summary
        try:
            resumed = await session_state_summary_manager.resume_task(
                user_id=user_id, task_id=task_id,
            )
            if resumed:
                logger.info("Session resumed from summary for task %s", task_id)
                return resumed
        except Exception as e:
            logger.warning("Failed to resume from summary for task %s: %s", task_id, e)

        return None

    async def inject_shard_on_resume(
        self, user_id: str, task_id: str, state: dict[str, Any],
    ) -> dict[str, Any]:
        """FR-SS-003: Inject session state summary into resumed session.

        Previously a no-op. Now loads the latest summary for the task
        and prepends the injection text to the session state, enabling
        cross-port continuation.
        """
        try:
            injection_text = await session_state_summary_manager.inject_summary(
                user_id=user_id, task_id=task_id,
            )
            if injection_text:
                state["injection_text"] = injection_text
                logger.info("Summary injected for task %s on resume", task_id)
            else:
                logger.debug("No summary found to inject for task %s", task_id)
        except Exception as e:
            logger.warning("Failed to inject summary on resume: %s", e)

        return state

    async def find_unfinished_tasks(self, user_id: str) -> list[dict[str, Any]]:
        """Find all unfinished tasks for a user across all ports.

        Delegates to SessionStateSummaryManager.find_unfinished_tasks.
        """
        return await session_state_summary_manager.find_unfinished_tasks(user_id)


# Global singleton
session_recovery = SessionRecoveryManager()
