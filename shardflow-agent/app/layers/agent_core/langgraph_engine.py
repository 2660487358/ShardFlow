# mypy: ignore-errors
"""LangGraph ReAct 引擎 — 个人助手版。

图结构（架构 v5.0）:
intent_recognize → profile_inject → llm_think → tool_execute → observe
    → check_state → (loop|shard_extract → strategy_search → END|strategy_save → END)

新增节点:
- profile_inject: 意图识别后注入用户画像
- strategy_search: 分片后检索历史策略
"""
import asyncio
import json
import logging
import re
from typing import Any

from langgraph.graph import END, StateGraph  # type: ignore[import-untyped]

logger = logging.getLogger(__name__)


class StreamingAnswerExtractor:
    """Extracts final_answer content from streaming LLM tokens in real-time.

    Supports two output formats:
    1. New format: <THINKING>...</THINKING><ANSWER>...</ANSWER> tags
    2. Legacy format: {"final_answer": "The answer text..."}

    For the new format, detects <ANSWER> tag and streams its content.
    For the legacy format, detects "final_answer" JSON key and streams its value.

    Tag detection uses regex patterns to handle whitespace variations
    (e.g., "</THINKING\n", "</THINKING ", "</ANSWER\n>").
    """

    # Regex patterns for robust tag detection (handles whitespace variations)
    _RE_THINKING_OPEN = re.compile(r"<THINKING\s*>")
    _RE_THINKING_CLOSE = re.compile(r"</THINKING\s*>")
    _RE_ANSWER_OPEN = re.compile(r"<ANSWER\s*>")
    _RE_ANSWER_CLOSE = re.compile(r"</ANSWER\s*>")

    def __init__(self) -> None:
        self._buffer = ""
        self._in_answer = False
        self._escape_next = False
        self._in_thinking = False
        self._format: str = ""  # "tag" or "json"
        self._tag_consumed = False  # whether we've consumed initial tags

    def feed(self, token: str) -> tuple[str | None, str | None]:
        """Feed a token and return (answer_content, thinking_content) extracted, or (None, None).

        Returns a tuple:
        - answer_content: any text that should be shown as the final answer
        - thinking_content: any text that belongs to the thinking section
        """
        self._buffer += token

        # Keep buffer manageable
        if len(self._buffer) > 800:
            self._buffer = self._buffer[-800:]

        # Auto-detect format on first significant content
        if not self._format:
            if self._RE_THINKING_OPEN.search(self._buffer) or self._RE_THINKING_CLOSE.search(self._buffer) or self._RE_ANSWER_OPEN.search(self._buffer):
                self._format = "tag"
            elif '"final_answer"' in self._buffer:
                self._format = "json"

        if self._format == "tag":
            return self._feed_tag_format(token)
        else:
            answer = self._feed_json_format(token)
            return answer, None

    def _feed_tag_format(self, token: str) -> tuple[str | None, str | None]:
        """Handle <THINKING>/<ANSWER> tag format with robust tag detection."""
        thinking_content = None
        answer_content = None

        # ---- Not yet in any section: look for THINKING or ANSWER open tag ----
        if not self._in_thinking and not self._in_answer:
            think_match = self._RE_THINKING_OPEN.search(self._buffer)
            ans_match = self._RE_ANSWER_OPEN.search(self._buffer)

            # Prefer THINKING if both found (THINKING comes first)
            if think_match:
                self._in_thinking = True
                after_tag = self._buffer[think_match.end():]
                self._buffer = ""
                if after_tag:
                    thinking_content, answer_content = self._process_thinking_content(after_tag)
                return answer_content, thinking_content

            if ans_match:
                self._in_answer = True
                after_tag = self._buffer[ans_match.end():]
                self._buffer = ""
                if after_tag:
                    answer_content, _ = self._process_answer_content(after_tag)
                return answer_content, None

            # No tag found yet — buffer the token, don't output anything
            # But check if buffer is getting large without finding tags
            # (might be plain text without tags)
            if len(self._buffer) > 200 and not self._format:
                # Likely no tags coming, treat as plain answer
                self._format = "json"  # fall back to legacy
                return None, None

            return None, None

        # ---- Inside THINKING section ----
        if self._in_thinking:
            thinking_content, answer_content = self._process_thinking_content(self._buffer)
            if self._RE_THINKING_CLOSE.search(self._buffer):
                self._buffer = ""
            else:
                # Keep only the tail that might contain a partial closing tag
                # (last 30 chars could be part of "</THINKING>")
                tail = self._buffer[-30:] if len(self._buffer) > 30 else self._buffer
                self._buffer = tail
                # Don't output the tail yet — it might be part of a tag
                if thinking_content and len(thinking_content) > len(tail):
                    thinking_content = thinking_content[:-len(tail)] if len(tail) < len(thinking_content) else None
                else:
                    thinking_content = None
            return answer_content, thinking_content

        # ---- Inside ANSWER section ----
        if self._in_answer:
            answer_content, done = self._process_answer_content(self._buffer)
            if done:
                self._buffer = ""
            else:
                # Keep tail that might contain partial closing tag
                tail = self._buffer[-25:] if len(self._buffer) > 25 else self._buffer
                self._buffer = tail
                if answer_content and len(answer_content) > len(tail):
                    answer_content = answer_content[:-len(tail)] if len(tail) < len(answer_content) else None
                else:
                    answer_content = None
            return answer_content, None

        return None, None

    def _process_thinking_content(self, text: str) -> tuple[str | None, str | None]:
        """Process text inside THINKING section. Returns (thinking_content, answer_content)."""
        close_match = self._RE_THINKING_CLOSE.search(text)
        if close_match:
            thinking_content = text[:close_match.start()]
            self._in_thinking = False
            remaining = text[close_match.end():]

            # Check for ANSWER start in remaining text
            ans_match = self._RE_ANSWER_OPEN.search(remaining)
            if ans_match:
                self._in_answer = True
                after_ans = remaining[ans_match.end():]
                answer_content = after_ans if after_ans else None
                return thinking_content or None, answer_content
            return thinking_content or None, None
        else:
            return text or None, None

    def _process_answer_content(self, text: str) -> tuple[str | None, bool]:
        """Process text inside ANSWER section. Returns (answer_content, is_done)."""
        close_match = self._RE_ANSWER_CLOSE.search(text)
        if close_match:
            answer_content = text[:close_match.start()]
            self._in_answer = False
            return answer_content or None, True
        else:
            return text or None, False

    def _feed_json_format(self, token: str) -> str | None:
        """Legacy format: detect "final_answer" JSON key."""
        if not self._in_answer:
            match = re.search(r'"final_answer"\s*:\s*"', self._buffer)
            if match:
                self._in_answer = True
                remaining = self._buffer[match.end():]
                self._buffer = ""
                if remaining:
                    return self._process_json_answer_chars(remaining)
            return None
        else:
            return self._process_json_answer_chars(token)

    def _process_json_answer_chars(self, text: str) -> str:
        """Process characters while inside the final_answer string value."""
        result: list[str] = []
        for char in text:
            if self._escape_next:
                self._escape_next = False
                if char == "n":
                    result.append("\n")
                elif char == "t":
                    result.append("\t")
                elif char == "\\":
                    result.append("\\")
                elif char == '"':
                    result.append('"')
                elif char == "/":
                    result.append("/")
                else:
                    result.append(char)
            elif char == "\\":
                self._escape_next = True
            elif char == '"':
                self._in_answer = False
                return "".join(result)
            else:
                result.append(char)
        return "".join(result)

    @property
    def in_answer(self) -> bool:
        return self._in_answer

    @property
    def in_thinking(self) -> bool:
        return self._in_thinking


def _extract_json_block(text: str) -> dict[str, Any] | None:
    """Extract a JSON object from LLM output, handling nested braces.

    Supports both new tag format and legacy format:
    - New: <THINKING>...</THINKING><ANSWER>json_or_text</ANSWER>
    - Legacy: raw text with ```json { ... } ``` blocks
    """
    # First, try to extract from <ANSWER> tag content
    answer_content = _extract_answer_tag_content(text)
    if answer_content:
        # Try to parse JSON from ANSWER content
        m = re.search(r"```json\s*(\{.*?\})\s*```", answer_content, re.DOTALL)
        if m:
            try:
                return json.loads(m.group(1))
            except (json.JSONDecodeError, IndexError):
                pass

        # Check if ANSWER content is pure text (final answer, no JSON)
        # This means the model gave a direct answer without tool call
        has_action_plan = "action_plan" in answer_content
        if not has_action_plan and answer_content.strip():
            return {"final_answer": answer_content.strip(), "is_done": True}

    # Fallback: legacy format
    # 1) Try fenced code block: ```json { ... } ```
    m = re.search(r"```json\s*(\{.*?\})\s*```", text, re.DOTALL)
    if m:
        try:
            return json.loads(m.group(1))
        except (json.JSONDecodeError, IndexError):
            return None
    # 2) Try to find balanced JSON object with action_plan key
    json_str = _find_balanced_json(text, "action_plan")
    if not json_str:
        # 3) Try to find balanced JSON object with final_answer key
        json_str = _find_balanced_json(text, "final_answer")
    if not json_str:
        return None
    try:
        return json.loads(json_str)
    except (json.JSONDecodeError, IndexError):
        return None


def _extract_answer_tag_content(text: str) -> str | None:
    """Extract content from <ANSWER>...</ANSWER> tags (robust regex version)."""
    ans_open = re.search(r"<ANSWER\s*>", text, re.IGNORECASE)
    if not ans_open:
        return None
    start = ans_open.end()
    ans_close = re.search(r"</ANSWER\s*>", text[start:], re.IGNORECASE)
    if not ans_close:
        return text[start:].strip()
    content = text[start:start + ans_close.start()].strip()
    # Safety net: strip any remaining tag markers
    content = re.sub(r'</?THINKING\s*>', '', content, flags=re.IGNORECASE)
    content = re.sub(r'</?ANSWER\s*>', '', content, flags=re.IGNORECASE)
    content = re.sub(r'</?THINKING(?!\s*>)[^>]*$', '', content, flags=re.IGNORECASE)
    content = re.sub(r'</?ANSWER(?!\s*>)[^>]*$', '', content, flags=re.IGNORECASE)
    return content.strip()


def _find_balanced_json(text: str, key: str) -> str | None:
    """Find a JSON object containing the given key using brace counting for nesting."""
    start_idx = text.find(f'"{key}"')
    if start_idx == -1:
        return None
    # Walk backward to find the opening brace
    brace_start = text.rfind("{", 0, start_idx)
    if brace_start == -1:
        return None
    # Walk forward from brace_start counting braces
    depth = 0
    for i in range(brace_start, len(text)):
        ch = text[i]
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return text[brace_start:i + 1]
    return None


# ---- 节点函数 ----

async def node_intent_recognize(state: dict[str, Any]) -> dict[str, Any]:
    """节点 1: 意图识别。

    若 API 层已注入意图结果（injected_intent），则直接复用，跳过重复的 LLM 调用。
    这是消除双重意图识别的优化——之前 API 层和图中各调用一次 LLM，增加 1.5-3s。
    """
    # 优化：复用 API 层已识别的意图，避免重复 LLM 调用
    if state.get("intent"):
        return state

    from app.layers.agent_core.llm_router import llm_router
    from app.layers.agent_core.prompt_engine import prompt_engine

    user_input: str = state.get("user_input", "")
    prompt = prompt_engine.build_intent_classify_prompt(user_input)
    model_id = state.get("model_id", llm_router.select_model("intent_recognition"))
    try:
        response = await llm_router.call_with_retry(prompt, model_id)
        content = await llm_router.extract_content(response)
        state["intent"] = content.strip().lower()
    except Exception:
        state["intent"] = "general_qa"
    return state


async def node_profile_inject(state: dict[str, Any]) -> dict[str, Any]:
    """节点 2: 画像注入（新增）。

    架构规则 AR-3: 每次推理前必须注入用户画像。
    从 UserProfileManager 加载画像并注入 Prompt 模板。
    """
    from app.layers.agent_core.user_profile_manager import user_profile_manager

    user_id = state.get("user_id", "")
    if user_id:
        profile = await user_profile_manager.load_profile(user_id)
        user_profile_manager.inject_profile(profile, state)
    else:
        state["profile_context"] = "暂无用户画像（用户未登录）"
        state["user_context"] = {}

    return state


async def node_llm_think(state: dict[str, Any]) -> dict[str, Any]:
    """节点 3: LLM 推理思考（流式输出版 — 输出行为规范版）。

    将 LLM 的流式 token 推入 state["_stream_queue"]，供 stream_react_events 实时 yield。
    支持 <THINKING>/<ANSWER> 标签格式和旧 JSON 格式。
    流式完成后解析完整文本中的 JSON 块获取 action_plan / final_answer。
    最终答案经过后处理清洗流水线。
    """
    from app.layers.agent_core.llm_router import llm_router
    from app.layers.agent_core.prompt_engine import prompt_engine
    from app.layers.reasoning.error_handler import error_handler

    # 加载历史 ContextShard（如果还没加载）
    if not state.get("context_shard_info"):
        try:
            from app.layers.agent_core.memory_orchestrator import memory_orchestrator
            from app.models.memory import MemoryType
            task_id = state.get("task_id", "")
            user_id = state.get("user_id", "")
            record = await memory_orchestrator.read(user_id, MemoryType.LONG_TERM, task_id)
            if record and record.data:
                from app.layers.agent_core.context_shard import context_shard_manager
                try:
                    from app.models.context_shard import ContextShard
                    shard = ContextShard(**record.data)
                    state["context_shard_info"] = context_shard_manager.inject_shard(shard, state)
                except Exception:
                    state["context_shard_info"] = "无（首次对话）"
        except Exception:
            pass

    prompt = prompt_engine.build_think_prompt(state)
    model_id = state.get("model_id", llm_router.select_model("think"))

    stream_queue: asyncio.Queue[bytes] | None = state.get("_stream_queue")
    from app.api.v1.response_formatter import response_formatter

    collected: list[str] = []
    max_retries = 2
    last_error: Exception | None = None

    for attempt in range(max_retries):
        collected.clear()
        extractor = StreamingAnswerExtractor()
        try:
            async for token in llm_router.call_stream_with_retry(prompt, model_id):
                collected.append(token)
                if stream_queue is not None:
                    # Feed token to extractor for real-time tag-based parsing
                    answer_chunk, thinking_chunk = extractor.feed(token)

                    # Stream thinking content — 经过 ThinkingContentFilter 二次清洗
                    # 规范 3.3.1: 展示内容需经过二次清洗（去除工具协议、内部状态）
                    if thinking_chunk:
                        try:
                            from app.layers.security.output_processor import ThinkingContentFilter
                            filtered_thinking = ThinkingContentFilter.filter_streaming_chunk(thinking_chunk)
                            if filtered_thinking:
                                await stream_queue.put(response_formatter.format_think(filtered_thinking))
                        except Exception:
                            await stream_queue.put(response_formatter.format_think(thinking_chunk))

                    # Stream answer content in real-time
                    if answer_chunk:
                        await stream_queue.put(response_formatter.format_answer(answer_chunk))
                        state["_answer_streamed"] = True

            content = "".join(collected)
            state["think_result"] = content

            parsed = _extract_json_block(content)
            if parsed:
                if "action_plan" in parsed:
                    state["action_plan"] = parsed["action_plan"]
                    state["is_done"] = False
                    return state
                elif "final_answer" in parsed:
                    # Apply post-processing pipeline to final answer
                    raw_answer = parsed["final_answer"]
                    processed = _apply_output_processing(raw_answer, content)
                    state["final_answer"] = processed
                    state["is_done"] = True
                    state["action_plan"] = {}
                    # If answer was not streamed in real-time, fall back to replay
                    if not state.get("_answer_streamed") and stream_queue is not None:
                        from app.layers.security.output_guard import output_guard
                        answer_text = output_guard.mask_pii(processed)
                        chunk_size = 3
                        for i in range(0, len(answer_text), chunk_size):
                            chunk = answer_text[i:i + chunk_size]
                            await stream_queue.put(response_formatter.format_answer(chunk))
                            await asyncio.sleep(0)
                        state["_answer_streamed"] = True
                    return state

            # No valid JSON parsed — retry if attempts remain
            if attempt < max_retries - 1:
                logger.warning("LLM think: no valid JSON in response, retrying (%d/%d)", attempt + 1, max_retries)
                continue
            # Final attempt: treat as done with raw content as answer
            # Apply post-processing to raw content
            processed = _apply_output_processing(content, content)
            state["final_answer"] = processed
            state["is_done"] = True
            state["action_plan"] = {}
            # Also stream via queue for the realtime answer mode
            if not state.get("_answer_streamed") and stream_queue is not None:
                from app.layers.security.output_guard import output_guard
                answer_text = output_guard.mask_pii(processed)
                chunk_size = 3
                for i in range(0, len(answer_text), chunk_size):
                    chunk = answer_text[i:i + chunk_size]
                    await stream_queue.put(response_formatter.format_answer(chunk))
                    await asyncio.sleep(0)
                state["_answer_streamed"] = True
            return state

        except Exception as e:
            last_error = e
            if attempt < max_retries - 1:
                logger.warning("LLM think stream error (attempt %d): %s", attempt + 1, e)
                await asyncio.sleep(1.0 * (2 ** attempt))
                continue

    # All retries exhausted
    state = error_handler.format_error_state(state, last_error or RuntimeError("LLM think failed"))
    state["action_plan"] = {}
    return state


def _apply_output_processing(answer: str, full_content: str) -> str:
    """Apply post-processing pipeline to the final answer.

    Runs the 5-step cleaning pipeline and applies degradation if needed.
    """
    try:
        from app.layers.security.output_processor import output_processor
        result = output_processor.process(full_content)
        if result.is_valid:
            return result.answer or answer
        else:
            # Degradation was applied
            logger.warning("Output processing applied degradation: %s", result.fallback_reason)
            return result.answer
    except Exception as e:
        logger.warning("Output processing failed, using raw answer: %s", e)
        return answer


async def node_tool_execute(state: dict[str, Any]) -> dict[str, Any]:
    """节点 4: 工具执行（支持内置工具 + MCP 工具）。"""
    # 早期退出：若已完成，跳过不必要的工具执行
    if state.get("is_done", False):
        return state

    from app.layers.tool.http_executor import http_executor
    from app.layers.tool.result_parser import result_parser
    from app.layers.tool.tool_registry import tool_registry

    action_plan = state.get("action_plan") or {}
    if not action_plan:
        state["observation"] = "no tool to execute"
        return state

    tool_name = action_plan.get("tool", "")
    tool_params = action_plan.get("params", {})
    source_type = action_plan.get("source_type", "unknown")

    # 检查是否为 MCP 工具
    if tool_name.startswith("mcp:"):
        try:
            from app.layers.agent_core.mcp_client import mcp_client
            from app.layers.security.mcp_security import mcp_security_gateway

            user_id = state.get("user_id", "")
            mcp_tool_name = tool_name[4:]  # 去掉 "mcp:" 前缀

            # 安全网关检查
            allowed, sanitized_params, reason = await mcp_security_gateway.gate_call(
                user_id, mcp_tool_name, tool_params,
                user_permissions=state.get("user_permissions", []),
            )
            if not allowed:
                mcp_security_gateway.audit_call(user_id, mcp_tool_name, tool_params, False, reason)
                state["observation"] = f"MCP tool blocked: {reason}"
                return state

            # 执行 MCP 调用
            result = await mcp_client.call_tool(mcp_tool_name, sanitized_params)
            mcp_security_gateway.audit_call(
                user_id, mcp_tool_name, sanitized_params, result.success,
                result.error, result.latency_ms,
            )

            if result.success and result.data:
                content = result.data.get("content", str(result.data))
                state["tool_result"] = result.data
                state["observation"] = content[:2000]  # 截断过长结果
            else:
                state["tool_result"] = None
                state["observation"] = result.error or f"MCP tool {mcp_tool_name} failed"
            return state
        except Exception as e:
            state["observation"] = f"MCP tool execution error: {e}"
            return state

    # 内置工具执行
    try:
        tool_meta = tool_registry.get(tool_name)
    except KeyError:
        state["observation"] = f"Tool not found: {tool_name}"
        return state

    url = tool_params.pop("url", "")
    result = await http_executor.execute_with_retry(tool_name, tool_params, url=url)

    if result.success and result.data:
        parsed = result_parser.parse(
            result.data if isinstance(result.data, dict) else {"raw": str(result.data)},
            source_type,
        )
        state["tool_result"] = parsed.model_dump()
        state["observation"] = parsed.snippet or f"Tool {tool_name} executed successfully"
    else:
        state["tool_result"] = None
        state["observation"] = result.error or f"Tool {tool_name} failed"

    return state


async def node_observe(state: dict[str, Any]) -> dict[str, Any]:
    """节点 5: 观察与反思。"""
    # 早期退出：若已标记完成，跳过不必要的 LLM 调用
    if state.get("is_done", False):
        return state

    from app.layers.agent_core.llm_router import llm_router
    from app.layers.agent_core.prompt_engine import prompt_engine
    from app.layers.reasoning.decision_reasoning import confidence_scorer

    prompt = prompt_engine.build_observe_prompt(state)
    model_id = state.get("model_id", llm_router.select_model("observe"))
    try:
        response = await llm_router.call_with_retry(prompt, model_id)
        content = await llm_router.extract_content(response)
        state["observation"] = content
    except Exception:
        state["observation"] = state.get("observation") or "Observation failed"

    tool_result = state.get("tool_result")
    if tool_result:
        confidence_scorer.score_individual_fact(
            tool_result if isinstance(tool_result, dict) else {"fact": str(tool_result)}
        )

    return state


async def node_check_state(state: dict[str, Any]) -> dict[str, Any]:
    """节点 6: 状态检查与循环控制。"""
    from app.layers.agent_core.context_manager import context_manager
    from app.layers.reasoning.error_handler import error_handler

    messages = state.get("messages", [])
    token_count = context_manager.estimate_tokens(messages)
    state["token_count"] = token_count
    state["context_usage_ratio"] = context_manager.get_context_usage(state)
    state["should_shard"] = context_manager.should_shard(state)

    if error_handler.handle_loop_limit(state):
        state = error_handler.format_loop_limit_state(state)
        return state

    loop_count: int = state.get("loop_count", 0)
    state["loop_count"] = loop_count + 1
    return state


async def node_shard_extract(state: dict[str, Any]) -> dict[str, Any]:
    """节点 7: 状态包提取。"""
    from app.layers.agent_core.context_shard import context_shard_manager
    from app.layers.agent_core.memory_orchestrator import memory_orchestrator
    from app.models.memory import MemoryType

    shard = await context_shard_manager.extract_shard(state)
    if shard is not None:
        shard_dict = shard.model_dump()
        state["current_shard"] = shard_dict
        state["shard_saved"] = True
        state["context_shard_info"] = context_shard_manager.inject_shard(shard, state)

        user_id = state.get("user_id", "")
        task_id = state.get("task_id", "")
        try:
            await memory_orchestrator.write_shard(user_id, task_id, shard_dict)
        except Exception:
            try:
                from app.infrastructure.callback_client import callback_client
                await callback_client.save_shard(shard_dict)
            except Exception:
                pass
    else:
        state["shard_saved"] = False
        state["observation"] = "Shard extraction skipped (context usage below threshold)"

    return state


async def node_strategy_search(state: dict[str, Any]) -> dict[str, Any]:
    """节点 8: 策略检索（新增）。

    架构要求在 shard_extract 后检索历史策略，为策略复用提供依据。
    """
    from app.layers.agent_core.strategy_engine import strategy_engine

    intent = state.get("intent", "general_qa")
    task_goal = state.get("user_input", "")
    user_id = state.get("user_id", "")

    try:
        # 检索历史策略
        results = await strategy_engine.search_strategy(
            task_type=intent,
            query_pattern=task_goal[:200],
            limit=5,
        )
        if results:
            decision = strategy_engine.reuse_decision(results)
            state["strategy_decision"] = decision.decision
            state["strategy_similarity"] = decision.similarity
            state["strategy_suggested_sources"] = decision.suggested_sources
            if decision.matched_record:
                state["strategy_matched_id"] = decision.matched_record.strategy_id
        else:
            state["strategy_decision"] = "COLD_START"
            state["strategy_similarity"] = 0.0
    except Exception:
        state["strategy_decision"] = "COLD_START"
        state["strategy_similarity"] = 0.0

    return state


async def node_strategy_save(state: dict[str, Any]) -> dict[str, Any]:
    """节点 9: 策略保存与收尾。"""
    from app.layers.agent_core.strategy_engine import strategy_engine
    from app.layers.agent_core.memory_orchestrator import memory_orchestrator
    from app.models.memory import MemoryType
    from app.models.strategy import SourceCombo, StrategyRecord

    intent = state.get("intent", "general_qa")
    final_answer = state.get("final_answer", "")
    loop_count = state.get("loop_count", 0)
    user_id = state.get("user_id", "")
    task_id = state.get("task_id", "")

    strategy_saved = False
    try:
        default_strategy = strategy_engine.get_default_strategy(intent)
        sources = default_strategy.get("sources", ["web_search"])
        weights = default_strategy.get("weights", {})

        record = StrategyRecord(
            strategy_id=f"strategy-{task_id}-{loop_count}",
            user_id=user_id,
            task_type=intent,
            query_pattern=final_answer[:200] if final_answer else "",
            source_combo=[
                SourceCombo(source=s, weight=weights.get(s, 0.5), reliability=0.7)
                for s in sources
            ],
            success_score=0.5,
            cost_ms=loop_count * 2000,
        )

        try:
            await memory_orchestrator.write_strategy(
                user_id, record.strategy_id, record.model_dump(),
            )
            strategy_saved = True
        except Exception:
            await strategy_engine.save_strategy(record)
            strategy_saved = True
    except Exception:
        strategy_saved = False

    state["strategy_saved"] = strategy_saved
    state["is_done"] = True
    return state


# ---- 路由函数 ----

def _route_after_check(state: dict[str, Any]) -> str:
    """check_state 后的条件路由。

    新版路由:
    - is_done → strategy_save (结束)
    - should_shard → shard_extract → strategy_search → END
    - context_usage < 80% → llm_think (继续循环)
    - context_usage >= 80% → shard_extract (即将超限，先保存)
    """
    if state.get("is_done", False):
        return "node_strategy_save"
    if state.get("should_shard", False):
        return "node_shard_extract"
    ratio: float = state.get("context_usage_ratio", 0)
    if ratio < 0.80:
        return "node_llm_think"
    return "node_shard_extract"


# ---- 图构建 ----

def build_react_graph() -> Any:
    """构建个人助手版 ReAct 图。

    新图结构:
    intent_recognize → profile_inject → llm_think → tool_execute → observe
        → check_state → (loop | shard_extract → strategy_search → END | strategy_save → END)
    """
    workflow: StateGraph = StateGraph(dict)  # type: ignore[type-arg]

    # 注册所有节点
    workflow.add_node("node_intent_recognize", node_intent_recognize)
    workflow.add_node("node_profile_inject", node_profile_inject)
    workflow.add_node("node_llm_think", node_llm_think)
    workflow.add_node("node_tool_execute", node_tool_execute)
    workflow.add_node("node_observe", node_observe)
    workflow.add_node("node_check_state", node_check_state)
    workflow.add_node("node_shard_extract", node_shard_extract)
    workflow.add_node("node_strategy_search", node_strategy_search)
    workflow.add_node("node_strategy_save", node_strategy_save)

    # 设置入口和边
    workflow.set_entry_point("node_intent_recognize")
    workflow.add_edge("node_intent_recognize", "node_profile_inject")
    workflow.add_edge("node_profile_inject", "node_llm_think")
    workflow.add_edge("node_llm_think", "node_tool_execute")
    workflow.add_edge("node_tool_execute", "node_observe")
    workflow.add_edge("node_observe", "node_check_state")

    # 条件路由
    workflow.add_conditional_edges(
        "node_check_state",
        _route_after_check,
        {
            "node_llm_think": "node_llm_think",
            "node_shard_extract": "node_shard_extract",
            "node_strategy_save": "node_strategy_save",
        },
    )

    # 分片后 → 策略检索 → 结束
    workflow.add_edge("node_shard_extract", "node_strategy_search")
    workflow.add_edge("node_strategy_search", END)

    # 策略保存 → 结束
    workflow.add_edge("node_strategy_save", END)

    return workflow.compile()


react_graph = build_react_graph()
