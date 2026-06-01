import asyncio
import json
import logging
from typing import Any, AsyncIterator

from starlette.requests import Request

from app.layers.agent_core.langgraph_engine import react_graph

logger = logging.getLogger(__name__)

SSE_EVENT_TYPES = {
    "intent": "intent",
    "think": "think",
    "action": "action",
    "observe": "observe",
    "shard_trigger": "shard_trigger",
    "shard_result": "shard_result",
    "shard_resume": "shard_resume",
    "strategy": "strategy",
    "profile_applied": "profile_applied",
    "progress": "progress",
    "done": "done",
    "error": "error",
    "heartbeat": "heartbeat",
}

# 兼容过渡：同时发送新旧事件类型，2周过渡期后移除
EVENT_ALIASES: dict[str, list[str]] = {
    "action": ["action", "tool_call_start"],
    "observe": ["observe", "tool_call_result"],
    "strategy": ["strategy", "strategy_found"],
}


class ResponseFormatter:
    def format_event(self, event_type: str, data: dict[str, Any]) -> str:
        payload = {"type": event_type, "data": data}
        return f"event: {event_type}\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"

    def format_event_with_aliases(self, event_type: str, data: dict[str, Any]) -> list[str]:
        """同时发送新旧事件类型（兼容过渡）"""
        results = [self.format_event(event_type, data)]
        for alias in EVENT_ALIASES.get(event_type, []):
            alias_data = dict(data)
            alias_payload = {"type": alias, "data": alias_data}
            results.append(f"event: {alias}\ndata: {json.dumps(alias_payload, ensure_ascii=False)}\n\n")
        return results

    def _emit(self, event_type: str, data: dict[str, Any]) -> str:
        """单事件发送（新旧类型）"""
        parts = self.format_event_with_aliases(event_type, data)
        return "".join(parts)

    def format_intent(self, intent: str, confidence: float) -> str:
        return self.format_event("intent", {"intent": intent, "confidence": confidence})

    def format_think(self, reasoning: str) -> str:
        return self.format_event("think", {"reasoning": reasoning})

    def format_action(self, tool: str, params: dict[str, Any]) -> str:
        return self._emit("action", {"tool": tool, "params": params})

    def format_observe(self, tool: str, result: str, success: bool = True, latency_ms: int = 0) -> str:
        return self._emit("observe", {"tool": tool, "result": result, "success": success, "latency_ms": latency_ms})

    def format_shard_trigger(self, context_usage: float, suggested: bool = True) -> str:
        return self.format_event("shard_trigger", {"context_usage": context_usage, "suggested": suggested})

    def format_shard_result(self, shard_id: str, summary: str) -> str:
        return self.format_event("shard_result", {"shard_id": shard_id, "summary": summary})

    def format_strategy(self, decision: str, similarity: float, strategy_id: str = "") -> str:
        return self._emit("strategy", {"decision": decision, "similarity": similarity, "strategy_id": strategy_id})

    def format_profile_applied(self, expertise_level: str, preferred_depth: str) -> str:
        return self.format_event("profile_applied", {"expertise_level": expertise_level, "preferred_depth": preferred_depth})

    def format_progress(self, loop: int, context_usage: float, status: str = "") -> str:
        return self.format_event("progress", {"loop": loop, "context_usage": context_usage, "status": status})

    def format_done(self, answer: str, shard_id: str = "") -> str:
        from app.layers.security.output_guard import output_guard
        masked_answer = output_guard.mask_pii(answer)
        return self.format_event("done", {"answer": masked_answer, "shard_id": shard_id})

    def format_error(self, code: str, message: str, recoverable: bool = False) -> str:
        return self.format_event("error", {"code": code, "message": message, "recoverable": recoverable})

    def format_shard_resume(self, shard_summary: dict[str, Any]) -> str:
        return self.format_event("shard_resume", shard_summary)

    def format_heartbeat(self) -> str:
        import time
        return self.format_event("heartbeat", {"timestamp": time.time()})


response_formatter = ResponseFormatter()


async def stream_react_events(state: dict[str, Any], request: Request | None = None) -> AsyncIterator[str]:
    formatter = response_formatter

    intent = state.get("intent", "general_qa")
    yield formatter.format_intent(intent, 0.9)

    heartbeat_task: asyncio.Task[None] | None = None
    streaming = True
    iteration_count = 0

    async def _heartbeat() -> None:
        while streaming:
            await asyncio.sleep(15)
            if streaming:
                pass

    try:
        async for event in react_graph.astream_events(state, version="v2"):
            iteration_count += 1

            if request and iteration_count % 5 == 0:
                if await request.is_disconnected():
                    logger.info("Client disconnected, stopping stream")
                    streaming = False
                    break

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
                output_str = str(output)[:1000]
                success = "error" not in output_str.lower() if output else True
                yield formatter.format_observe(
                    data.get("name", "unknown"),
                    output_str,
                    success=success,
                )

            elif kind == "on_chain_end":
                output = event.get("data", {}).get("output", {})
                if not isinstance(output, dict):
                    continue

                if node_name == "node_profile_inject":
                    user_context = output.get("user_context", {})
                    yield formatter.format_profile_applied(
                        user_context.get("expertise_level", "intermediate"),
                        user_context.get("preferred_depth", "OVERVIEW"),
                    )

                elif node_name == "node_check_state":
                    loop = output.get("loop_count", 0)
                    usage = output.get("context_usage_ratio", 0)
                    if output.get("should_shard"):
                        yield formatter.format_shard_trigger(usage)
                    yield formatter.format_progress(loop, usage)

                elif node_name == "node_shard_extract":
                    shard = output.get("current_shard", {})
                    shard_id = shard.get("task_id", state.get("task_id", ""))
                    summary = str(shard.get("knowledge_state", {}).get("confirmed", []))[:500]
                    yield formatter.format_shard_result(shard_id, summary)

                elif node_name == "node_strategy_search":
                    decision = output.get("strategy_decision", "COLD_START")
                    similarity = float(output.get("strategy_similarity", 0.0))
                    matched_id = output.get("strategy_matched_id", "")
                    yield formatter.format_strategy(decision, similarity, matched_id)

    except Exception as e:
        yield formatter.format_error("STREAM_ERROR", str(e))

    streaming = False
    yield formatter.format_done(state.get("final_answer", "Inference complete"))
