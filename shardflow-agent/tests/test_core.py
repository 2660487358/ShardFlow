import pytest

from app.layers.agent_core.context_manager import context_manager
from app.layers.reasoning.error_handler import ErrorCategory, error_handler
from app.layers.agent_core.llm_router import llm_router
from app.layers.agent_core.prompt_engine import prompt_engine
from app.models.kb_state import create_initial_state


class TestPromptEngine:
    def test_load_known_template(self):
        template = prompt_engine.load_template("system_think")
        assert "任务目标" in template
        assert "{task_goal}" in template

    def test_load_unknown_template_raises(self):
        with pytest.raises(ValueError, match="Unknown template"):
            prompt_engine.load_template("nonexistent")

    def test_assemble_prompt(self):
        result = prompt_engine.assemble_prompt("Hello {name}", {"name": "World"})
        assert result == "Hello World"

    def test_build_think_prompt(self):
        state = create_initial_state("u1", "user1", "sess1", "理清 Dubbo 注册链路")
        result = prompt_engine.build_think_prompt(state)
        assert "理清 Dubbo 注册链路" in result
        assert "已知上下文" in result

    def test_build_intent_classify_prompt(self):
        result = prompt_engine.build_intent_classify_prompt("修复 NPE 异常")
        assert "code_exploration" in result
        assert "修复 NPE 异常" in result

    def test_all_templates_loadable(self):
        for name in prompt_engine.TEMPLATES:
            assert prompt_engine.load_template(name) is not None


class TestContextManager:
    def test_estimate_tokens(self):
        tokens = context_manager.estimate_tokens([{"content": "hello world" * 100}])
        assert tokens > 0

    def test_empty_messages(self):
        tokens = context_manager.estimate_tokens([])
        assert tokens == 0

    def test_check_budget_within_limit(self):
        state = {"token_count": 1000}
        assert context_manager.check_budget(state) is True

    def test_check_budget_over_limit(self):
        state = {"token_count": 200000}
        assert context_manager.check_budget(state) is False

    def test_get_context_usage(self):
        state = {"token_count": 0}
        usage = context_manager.get_context_usage(state)
        assert usage == 0.0

    def test_should_compress_below_threshold(self):
        state = {"token_count": 0}
        assert context_manager.should_compress(state) is False

    def test_should_shard_below_threshold(self):
        state = {"token_count": 0}
        assert context_manager.should_shard(state) is False

    def test_manage_window_truncates(self):
        msgs = [{"content": f"msg{i}"} for i in range(20)]
        result = context_manager.manage_window(msgs, max_recent=10)
        assert len(result) == 10

    def test_manage_window_no_truncation(self):
        msgs = [{"content": f"msg{i}"} for i in range(5)]
        result = context_manager.manage_window(msgs, max_recent=10)
        assert len(result) == 5

    def test_summarize_history(self):
        msgs = [{"content": "Found auth module"}, {"content": "JWT token verified"}]
        summary = context_manager.summarize_history(msgs)
        assert "auth" in summary
        assert "JWT" in summary


class TestErrorHandler:
    def test_classify_timeout(self):
        category = error_handler.classify_error(TimeoutError("timeout"))
        assert category == ErrorCategory.RETRYABLE

    def test_classify_auth_error(self):
        category = error_handler.classify_error(Exception("auth 401"))
        assert category == ErrorCategory.FATAL

    def test_classify_rate_limit(self):
        category = error_handler.classify_error(Exception("rate limit 429"))
        assert category == ErrorCategory.RETRYABLE

    def test_handle_llm_error_with_retries(self):
        result = error_handler.handle_llm_error(TimeoutError(), retries_left=2)
        assert result["action"] == "retry"
        assert result["retries_left"] == 1

    def test_handle_llm_error_no_retries(self):
        result = error_handler.handle_llm_error(Exception("unknown"), retries_left=0)
        assert result["action"] == "fail"

    def test_handle_loop_limit_under(self):
        state = {"loop_count": 5}
        assert error_handler.handle_loop_limit(state) is False

    def test_handle_loop_limit_over(self):
        state = {"loop_count": 20}
        assert error_handler.handle_loop_limit(state) is True

    def test_format_error_state(self):
        state = {"loop_count": 3}
        result = error_handler.format_error_state(state, Exception("test error"))
        assert result["is_done"] is True
        assert "test error" in result["error"]


class TestLLMRouter:
    def test_select_model_intent(self):
        model = llm_router.select_model("intent_recognition")
        assert "mini" in model

    def test_select_model_think(self):
        model = llm_router.select_model("think")
        assert "gpt-4o" in model

    def test_fallback_model(self):
        model = llm_router.fallback_model()
        assert "mini" in model


class TestCreateInitialState:
    def test_creates_state_with_defaults(self):
        state = create_initial_state("u1", "user1", "sess1", "test input")
        assert state["task_id"] == "u1"
        assert state["user_id"] == "user1"
        assert state["session_id"] == "sess1"
        assert state["user_input"] == "test input"
        assert state["loop_count"] == 0
        assert state["is_done"] is False
        assert state["context_usage_ratio"] == 0.0
