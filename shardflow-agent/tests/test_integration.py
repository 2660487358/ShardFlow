import json

from app.api.v1.response_formatter import response_formatter


class TestResponseFormatter:
    def test_format_intent_event(self):
        result = response_formatter.format_intent("code_exploration", 0.95)
        assert "event: intent" in result
        data = result.split("data: ")[1]
        payload = json.loads(data)
        assert payload["type"] == "intent"
        assert payload["data"]["intent"] == "code_exploration"

    def test_format_think_event(self):
        result = response_formatter.format_think("Analyzing dependencies")
        assert "event: think" in result
        payload = json.loads(result.split("data: ")[1])
        assert "Analyzing dependencies" in payload["data"]["reasoning"]

    def test_format_action_event(self):
        result = response_formatter.format_action("read_file", {"path": "test.java"})
        assert "event: action" in result
        payload = json.loads(result.split("data: ")[1])
        assert payload["data"]["tool"] == "read_file"

    def test_format_observe_event(self):
        result = response_formatter.format_observe("read_file", "file contents")
        assert "event: observe" in result

    def test_format_shard_trigger(self):
        result = response_formatter.format_shard_trigger(0.83)
        assert "event: shard_trigger" in result
        payload = json.loads(result.split("data: ")[1])
        assert payload["data"]["context_usage"] == 0.83

    def test_format_shard_result(self):
        result = response_formatter.format_shard_result("shard-001", "3 confirmed facts")
        assert "event: shard_result" in result

    def test_format_strategy(self):
        result = response_formatter.format_strategy("AUTO_REUSE", 0.88)
        assert "event: strategy" in result

    def test_format_progress(self):
        result = response_formatter.format_progress(3, 0.65)
        assert "event: progress" in result

    def test_format_done(self):
        result = response_formatter.format_done("Task complete", "shard-001")
        assert "event: done" in result
        payload = json.loads(result.split("data: ")[1])
        assert payload["data"]["answer"] == "Task complete"

    def test_format_error(self):
        result = response_formatter.format_error("LLM_TIMEOUT", "Request timed out")
        assert "event: error" in result

    def test_all_event_types_have_methods(self):
        for event_type in ["intent", "think", "action", "observe", "shard_trigger",
                           "shard_result", "strategy", "progress", "done", "error"]:
            assert hasattr(response_formatter, f"format_{event_type}") or \
                   hasattr(response_formatter, "format_" + event_type)
