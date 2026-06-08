import json

from app.api.v1.response_formatter import response_formatter


class TestResponseFormatter:
    @staticmethod
    def _parse_first_event(result: bytes) -> dict:
        """Helper: parse the first SSE event from the bytes result into the payload dict."""
        text = result.decode("utf-8")
        # Extract the first "data: {...}" line as JSON
        for line in text.split("\n"):
            if line.startswith("data: "):
                return json.loads(line[6:])
        raise ValueError("No data line found in SSE output")

    def test_format_intent_event(self):
        result = response_formatter.format_intent("code_exploration", 0.95)
        assert b"event: intent" in result
        payload = self._parse_first_event(result)
        assert payload["type"] == "intent"
        assert payload["data"]["intent"] == "code_exploration"

    def test_format_think_event(self):
        result = response_formatter.format_think("Analyzing dependencies")
        assert b"event: think" in result
        payload = self._parse_first_event(result)
        assert "Analyzing dependencies" in payload["data"]["reasoning"]

    def test_format_action_event(self):
        result = response_formatter.format_action("read_file", {"path": "test.java"})
        assert b"event: action" in result
        payload = self._parse_first_event(result)
        assert payload["data"]["tool"] == "read_file"

    def test_format_observe_event(self):
        result = response_formatter.format_observe("read_file", "file contents")
        assert b"event: observe" in result

    def test_format_shard_trigger(self):
        result = response_formatter.format_shard_trigger(0.83)
        assert b"event: shard_trigger" in result
        payload = self._parse_first_event(result)
        assert payload["data"]["context_usage"] == 0.83

    def test_format_shard_result(self):
        result = response_formatter.format_shard_result("shard-001", "3 confirmed facts")
        assert b"event: shard_result" in result

    def test_format_strategy(self):
        result = response_formatter.format_strategy("AUTO_REUSE", 0.88)
        assert b"event: strategy" in result

    def test_format_progress(self):
        result = response_formatter.format_progress(3, 0.65)
        assert b"event: progress" in result

    def test_format_done(self):
        result = response_formatter.format_done("Task complete", "shard-001")
        assert b"event: done" in result
        payload = self._parse_first_event(result)
        assert payload["data"]["answer"] == "Task complete"

    def test_format_error(self):
        result = response_formatter.format_error("LLM_TIMEOUT", "Request timed out")
        assert b"event: error" in result

    def test_all_event_types_have_methods(self):
        for event_type in ["intent", "think", "action", "observe", "shard_trigger",
                           "shard_result", "strategy", "progress", "done", "error"]:
            assert hasattr(response_formatter, f"format_{event_type}") or \
                   hasattr(response_formatter, "format_" + event_type)
