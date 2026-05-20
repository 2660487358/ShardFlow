import json
from typing import Any, AsyncIterator

from app.layers.agent_core.langgraph_engine import react_graph

SSE_EVENT_TYPES = {
    "intent": "intent",
    "think": "think",
    "action": "action",
    "observe": "observe",
    "shard_trigger": "shard_trigger",
    "shard_result": "shard_result",
    "strategy": "strategy",
    "progress": "progress",
    "done": "done",
    "error": "error",
}


class ResponseFormatter:
    def format_event(self, event_type: str, data: dict[str, Any]) -> str:
        payload = {"type": event_type, "data": data}
        return f"event: {event_type}\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"

    def format_intent(self, intent: str, confidence: float) -> str:
        return self.format_event("intent", {"intent": intent, "confidence": confidence})

    def format_think(self, reasoning: str) -> str:
        return self.format_event("think", {"reasoning": reasoning})

    def format_action(self, tool: str, params: dict[str, Any]) -> str:
        return self.format_event("action", {"tool": tool, "params": params})

    def format_observe(self, tool: str, result: str) -> str:
        return self.format_event("observe", {"tool": tool, "result": result})

    def format_shard_trigger(self, context_usage: float) -> str:
        return self.format_event("shard_trigger", {"context_usage": context_usage, "suggested": True})

    def format_shard_result(self, shard_id: str, summary: str) -> str:
        return self.format_event("shard_result", {"shard_id": shard_id, "summary": summary})

    def format_strategy(self, decision: str, similarity: float) -> str:
        return self.format_event("strategy", {"decision": decision, "similarity": similarity})

    def format_progress(self, loop: int, context_usage: float) -> str:
        return self.format_event("progress", {"loop": loop, "context_usage": context_usage})

    def format_done(self, answer: str, shard_id: str = "") -> str:
        return self.format_event("done", {"answer": answer, "shard_id": shard_id})

    def format_error(self, code: str, message: str) -> str:
        return self.format_event("error", {"code": code, "message": message})

    def format_shard_resume(self, shard_summary: dict[str, Any]) -> str:
        return self.format_event("shard_resume", shard_summary)


response_formatter = ResponseFormatter()


async def stream_react_events(state: dict[str, Any]) -> AsyncIterator[str]:
    formatter = response_formatter

    intent = state.get("intent", "general_qa")
    yield formatter.format_intent(intent, 0.9)

    try:
        async for event in react_graph.astream_events(state, version="v2"):
            kind = event.get("event", "")
            node_name = event.get("name", "")

            if kind == "on_chat_model_stream" and "think" in node_name:
                chunk = event.get("data", {}).get("chunk", {})
                content = getattr(chunk, "content", "")
                if content:
                    yield formatter.format_think(str(content))

            elif kind == "on_tool_start":
                data = event.get("data", {})
                yield formatter.format_action(
                    data.get("name", "unknown"),
                    data.get("input", {}),
                )

            elif kind == "on_tool_end":
                data = event.get("data", {})
                output = data.get("output", "")
                yield formatter.format_observe(
                    data.get("name", "unknown"),
                    str(output)[:1000],
                )

            elif kind == "on_chain_end" and node_name == "node_check_state":
                output = event.get("data", {}).get("output", {})
                if isinstance(output, dict):
                    loop = output.get("loop_count", 0)
                    usage = output.get("context_usage_ratio", 0)
                    yield formatter.format_progress(loop, usage)

    except Exception as e:
        yield formatter.format_error("STREAM_ERROR", str(e))

    yield formatter.format_done(state.get("final_answer", "Inference complete"))
