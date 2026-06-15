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
    "answer": "answer",
    "action": "action",
    "observe": "observe",
    "progress": "progress",
    "done": "done",
    "error": "error",
    "heartbeat": "heartbeat",
    "context_pressure": "context_pressure",
    "session_switching": "session_switching",
    "memory_context": "memory_context",
}

# 兼容过渡：同时发送新旧事件类型，2周过渡期后移除
EVENT_ALIASES: dict[str, list[str]] = {
    "action": ["action", "tool_call_start"],
    "observe": ["observe", "tool_call_result"],
}


class ResponseFormatter:
    def format_event(self, event_type: str, data: dict[str, Any]) -> bytes:
        payload = {"type": event_type, "data": data}
        text = f"event: {event_type}\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"
        return text.encode("utf-8")

    def format_event_with_aliases(self, event_type: str, data: dict[str, Any]) -> list[bytes]:
        """同时发送新旧事件类型（兼容过渡）"""
        results = [self.format_event(event_type, data)]
        for alias in EVENT_ALIASES.get(event_type, []):
            alias_data = dict(data)
            alias_payload = {"type": alias, "data": alias_data}
            text = f"event: {alias}\ndata: {json.dumps(alias_payload, ensure_ascii=False)}\n\n"
            results.append(text.encode("utf-8"))
        return results

    def _emit(self, event_type: str, data: dict[str, Any]) -> bytes:
        """单事件发送（新旧类型）"""
        parts = self.format_event_with_aliases(event_type, data)
        return b"".join(parts)

    def format_intent(self, intent: str, confidence: float) -> bytes:
        return self.format_event("intent", {"intent": intent, "confidence": confidence})

    def format_think(self, reasoning: str) -> bytes:
        return self.format_event("think", {"reasoning": reasoning})

    def format_answer(self, chunk: str) -> bytes:
        return self.format_event("answer", {"content": chunk})

    def format_action(self, tool: str, params: dict[str, Any]) -> bytes:
        """Format tool call start event.

        企业级Agent模型输出行为规范: 工具名称和参数不得暴露给用户。
        仅发送信号告知前端工具调用已开始，不暴露具体工具名和参数。
        """
        return self._emit("action", {"tool": "tool", "params": {}})

    def format_observe(self, tool: str, result: str, success: bool = True, latency_ms: int = 0) -> bytes:
        """Format tool execution result event.

        企业级Agent模型输出行为规范:
        - 工具名称: 不展示
        - 调用参数: 不展示
        - 执行耗时: 不展示（除非用户询问性能）
        - 数据来源: 展示（来源卡片/脚注）
        - 结果摘要: 展示（自然语言概括）
        """
        # 不暴露工具名和耗时，仅传递成功状态和结果摘要
        return self._emit("observe", {
            "success": success,
            "result": result[:500] if result else "",
        })

    def format_kb_search(self, results: list[dict]) -> bytes:
        """Format knowledge base search results event for frontend display."""
        return self._emit("kb_search", {"results": results[:5]})

    def format_shard_trigger(self, context_usage: float, suggested: bool = True) -> bytes:
        return self.format_event("shard_trigger", {"context_usage": context_usage, "suggested": suggested})

    def format_context_pressure(self, level: str, usage_ratio: float,
                                 current_tokens: int, context_limit: int) -> bytes:
        messages = {
            "warning": "上下文使用率已达60%",
            "critical": "上下文使用率已达80%，建议切换以保证输出质量",
            "full": "上下文已满，请选择操作",
        }
        return self.format_event("context_pressure", {
            "level": level,
            "usage_ratio": usage_ratio,
            "current_tokens": current_tokens,
            "context_limit": context_limit,
            "message": messages.get(level, ""),
        })

    def format_session_switching(self, summary_id: str, new_session_id: str) -> bytes:
        return self.format_event("session_switching", {
            "summary_id": summary_id,
            "new_session_id": new_session_id,
            "status": "ready",
        })

    def format_shard_result(self, shard_id: str, summary: str) -> bytes:
        return self.format_event("shard_result", {"shard_id": shard_id, "summary": summary})

    def format_strategy(self, decision: str, similarity: float, strategy_id: str = "") -> bytes:
        return self._emit("strategy", {"decision": decision, "similarity": similarity, "strategy_id": strategy_id})

    def format_profile_applied(self, expertise_level: str, preferred_depth: str) -> bytes:
        return self.format_event("profile_applied", {"expertise_level": expertise_level, "preferred_depth": preferred_depth})

    def format_progress(self, loop: int, context_usage: float, status: str = "") -> bytes:
        return self.format_event("progress", {"loop": loop, "context_usage": context_usage, "status": status})

    def format_done(self, answer: str) -> bytes:
        from app.layers.security.output_guard import output_guard
        masked_answer = output_guard.mask_pii(answer)
        return self.format_event("done", {"answer": masked_answer})

    def format_error(self, code: str, message: str, recoverable: bool = False) -> bytes:
        return self.format_event("error", {"code": code, "message": message, "recoverable": recoverable})

    def format_shard_resume(self, shard_summary: dict[str, Any]) -> bytes:
        return self.format_event("shard_resume", shard_summary)

    def format_memory_context(self, context_shard_info: str, profile_context: str = "",
                               episodic_context: str = "") -> bytes:
        """Format memory context injection event for frontend display.

        3D-01: 产出 memory_context SSE 事件，前端可展示记忆注入摘要。
        """
        return self.format_event("memory_context", {
            "context_shard_info": context_shard_info[:500] if context_shard_info else "",
            "profile_context": profile_context[:300] if profile_context else "",
            "episodic_context": episodic_context[:300] if episodic_context else "",
            "has_memory": bool(context_shard_info or profile_context or episodic_context),
        })

    def format_heartbeat(self) -> bytes:
        import time
        return self.format_event("heartbeat", {"timestamp": time.time()})


response_formatter = ResponseFormatter()


async def stream_react_events(state: dict[str, Any], request: Request | None = None, intent_confidence: float = 0.5) -> AsyncIterator[bytes]:
    """Stream ReAct graph events as SSE, with real-time LLM token delivery.

    Architecture: single-queue, single-consumer.
    - A background task (_process_graph) iterates over astream_events and pushes
      ALL formatted events (graph events) into the shared queue.
    - node_llm_think also pushes think/answer tokens into the same queue.
    - The main loop simply drains the queue item-by-item and yields them.
    This guarantees FIFO ordering with no race conditions or interleaving.
    """
    formatter = response_formatter

    intent = state.get("intent", "general_qa")
    yield formatter.format_intent(intent, intent_confidence)

    # Shared queue: both node_llm_think and _process_graph write here.
    # None is used as a sentinel to signal graph completion.
    stream_queue: asyncio.Queue[bytes | None] = asyncio.Queue()
    state["_stream_queue"] = stream_queue

    streaming = True

    async def _heartbeat() -> None:
        while streaming:
            await asyncio.sleep(15)
            if streaming:
                await stream_queue.put(formatter.format_heartbeat())

    async def _process_graph() -> None:
        """Iterate over LangGraph astream_events and push formatted events to the queue."""
        try:
            async for event in react_graph.astream_events(state, version="v2"):
                kind = event.get("event", "")
                node_name = event.get("name", "")

                if kind == "on_tool_start":
                    data = event.get("data", {})
                    await stream_queue.put(formatter.format_action(
                        data.get("name", "unknown"),
                        data.get("input", {}),
                    ))

                elif kind == "on_tool_end":
                    data = event.get("data", {})
                    output = data.get("output", "")
                    output_str = str(output)[:1000]

                    success = True
                    if hasattr(output, 'status'):
                        success = getattr(output, 'status') != 'error'
                    elif hasattr(output, 'response_metadata'):
                        pass
                    elif isinstance(output, str) and output:
                        error_indicators = ('Error:', 'Exception:', 'Traceback', 'Failed:')
                        success = not output.startswith(error_indicators)

                    await stream_queue.put(formatter.format_observe(
                        data.get("name", "unknown"),
                        output_str,
                        success=success,
                    ))

                elif kind == "on_chain_end":
                    output = event.get("data", {}).get("output", {})
                    if not isinstance(output, dict):
                        continue

                    if node_name == "node_check_state":
                        loop = output.get("loop_count", 0)
                        usage = output.get("context_usage_ratio", 0)
                        await stream_queue.put(formatter.format_progress(loop, usage))

                        pressure = output.get("_context_pressure")
                        if pressure:
                            await stream_queue.put(formatter.format_context_pressure(
                                pressure["level"],
                                pressure["usage_ratio"],
                                pressure["current_tokens"],
                                pressure["context_limit"],
                            ))
        except Exception as e:
            await stream_queue.put(formatter.format_error("GRAPH_ERROR", str(e)))
        finally:
            # Sentinel: signal the main loop that the graph is done
            await stream_queue.put(None)

    heartbeat_task: asyncio.Task[None] | None = None
    graph_task: asyncio.Task[None] | None = None

    try:
        heartbeat_task = asyncio.create_task(_heartbeat())
        graph_task = asyncio.create_task(_process_graph())

        disconnect_check_counter = 0

        while streaming:
            try:
                item = await asyncio.wait_for(stream_queue.get(), timeout=2.0)
            except asyncio.TimeoutError:
                # Periodic disconnect check
                if request:
                    disconnect_check_counter += 1
                    if disconnect_check_counter % 3 == 0:
                        if await request.is_disconnected():
                            logger.info("Client disconnected, stopping stream")
                            streaming = False
                            break
                continue

            # Sentinel: graph finished
            if item is None:
                break

            yield item

            # Yield to event loop so the SSE chunk can be flushed immediately
            await asyncio.sleep(0)

    except Exception as e:
        yield formatter.format_error("STREAM_ERROR", str(e))

    streaming = False

    # Cancel background tasks
    if graph_task and not graph_task.done():
        graph_task.cancel()
    if heartbeat_task and not heartbeat_task.done():
        heartbeat_task.cancel()

    # Final drain: flush any remaining items in the queue
    while not stream_queue.empty():
        try:
            item = stream_queue.get_nowait()
            if item is not None:
                yield item
        except asyncio.QueueEmpty:
            break

    # Clean up the queue reference
    if "_stream_queue" in state:
        del state["_stream_queue"]

    # Answer streaming: controlled by SF_AGENT_ANSWER_STREAMING_MODE config.
    # "realtime" (default): answer events streamed in real-time via node_llm_think
    #   → stream_queue, eliminating the artificial 2-char/10ms buffer replay.
    # "buffer": legacy mode — full answer replayed post-graph with 2-char chunks + 10ms delay.
    # If answer was already streamed during think phase, skip the replay entirely.
    from app.config import settings
    final_answer = state.get("final_answer", "")
    answer_was_streamed = state.get("_answer_streamed", False)

    if final_answer and not answer_was_streamed and settings.answer_streaming_mode == "buffer":
        from app.layers.security.output_guard import output_guard
        masked_answer = output_guard.mask_pii(final_answer)
        chunk_size = 2
        for i in range(0, len(masked_answer), chunk_size):
            chunk = masked_answer[i:i + chunk_size]
            yield formatter.format_answer(chunk)
            await asyncio.sleep(0.01)

    yield formatter.format_done(state.get("final_answer", ""))
