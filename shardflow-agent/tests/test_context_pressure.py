"""Unit tests for ContextManager cooldown mechanism and context switch API."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.layers.agent_core.context_manager import ContextManager


class TestContextPressure:
    """Tests for ContextManager pressure levels and cooldown mechanism."""

    def test_no_pressure_below_60(self):
        cm = ContextManager()
        usable = cm._usable_tokens()
        tokens_at_55 = int(usable * 0.55)
        state = {"token_count": tokens_at_55}
        level = cm.get_pressure_level(state)
        assert level is None

    def test_warning_at_60(self):
        cm = ContextManager()
        usable = cm._usable_tokens()
        tokens_at_62 = int(usable * 0.62)
        state = {"token_count": tokens_at_62}
        level = cm.get_pressure_level(state)
        assert level == "warning"

    def test_critical_at_80(self):
        cm = ContextManager()
        usable = cm._usable_tokens()
        tokens_at_82 = int(usable * 0.82)
        state = {"token_count": tokens_at_82}
        level = cm.get_pressure_level(state)
        assert level == "critical"

    def test_full_at_100(self):
        cm = ContextManager()
        usable = cm._usable_tokens()
        tokens_at_full = int(usable * 1.0) + 1
        state = {"token_count": tokens_at_full}
        level = cm.get_pressure_level(state)
        assert level == "full"

    def test_cooldown_prevents_refire(self):
        cm = ContextManager()
        usable = cm._usable_tokens()
        state = {"token_count": int(usable * 0.65)}

        level1 = cm.get_pressure_level(state)
        assert level1 == "warning"

        level2 = cm.get_pressure_level(state)
        assert level2 is None  # cooldown active

    def test_cooldown_resets_after_drop(self):
        cm = ContextManager()
        usable = cm._usable_tokens()
        state_high = {"token_count": int(usable * 0.65)}
        state_low = {"token_count": int(usable * 0.50)}

        level1 = cm.get_pressure_level(state_high)
        assert level1 == "warning"

        cm.get_pressure_level(state_low)  # triggers _update_cooldowns, usage 50% < 55%
        level2 = cm.get_pressure_level(state_high)
        assert level2 == "warning"  # re-fires after cooldown reset

    def test_most_severe_fires_first(self):
        cm = ContextManager()
        usable = cm._usable_tokens()
        # Jump from below warning to above critical
        state = {"token_count": int(usable * 0.90)}
        level = cm.get_pressure_level(state)
        assert level == "critical"

    def test_full_blocks_lower_levels(self):
        cm = ContextManager()
        usable = cm._usable_tokens()
        state = {"token_count": int(usable * 1.0) + 1}
        level = cm.get_pressure_level(state)
        assert level == "full"


class TestContextSwitchAPI:
    """Tests for the context switch API endpoint."""

    @pytest.mark.asyncio
    async def test_switch_returns_new_session_id(self):
        from app.api.v1.context_switch import ContextSwitchRequest, switch_context

        req = ContextSwitchRequest(
            user_id="user_001",
            task_id="task_001",
            session_id="sess_001",
            preview_enabled=False,
        )

        mock_wm_data = MagicMock()
        mock_wm_data.messages = []
        mock_wm_data.context_summary = ""
        mock_wm_data.task_type = "research"
        mock_wm_data.intent_stack = ["research"]

        mock_summary = MagicMock()
        mock_summary.summary_id = "ss_test_001"

        # The context_switch function imports lazily inside the function body,
        # so we need to patch the names from the app.layers.agent_core modules.
        # When switch_context runs `from app.layers.agent_core.working_memory_manager import ...`,
        # the binding is local. We must patch the module-level objects where they live.
        with patch(
            "app.layers.agent_core.working_memory_manager.working_memory_manager"
        ) as wm_mock, patch(
            "app.layers.agent_core.session_state_summary_manager.session_state_summary_manager"
        ) as sss_mock, patch(
            "app.layers.agent_core.memory_orchestrator.memory_orchestrator"
        ) as mo_mock:

            wm_mock.get_session.return_value = mock_wm_data
            sss_mock.extract_summary = AsyncMock(return_value=mock_summary)
            mo_mock.write_summary = AsyncMock(return_value=None)

            result = await switch_context(req)

            assert result["status"] == "ready"
            assert result["new_session_id"].startswith("sess_")
            assert result["summary_id"] == "ss_test_001"

    @pytest.mark.asyncio
    async def test_switch_rejects_unknown_session(self):
        from app.api.v1.context_switch import ContextSwitchRequest, switch_context
        from fastapi import HTTPException

        req = ContextSwitchRequest(
            user_id="user_001",
            task_id="task_001",
            session_id="sess_unknown",
        )

        with patch(
            "app.layers.agent_core.working_memory_manager.working_memory_manager"
        ) as wm_mock:
            wm_mock.get_session.return_value = None

            with pytest.raises(HTTPException) as exc_info:
                await switch_context(req)

            assert exc_info.value.status_code == 400
            assert "Unknown or stale session_id" in exc_info.value.detail
