"""记忆压缩 Prompt 模板 (T3.4).

为 L2 概念摘要（Concept Summary）提供版本化的 Prompt 模板，覆盖：
- 增量压缩：已有摘要 + 新增溢出消息 → 更新后的双版本摘要
- 校正压缩：已有摘要 + 当前窗口 → 校正后的完整摘要

输出格式严格约束为两部分：
1. natural_summary: 自然语言摘要（100 字以内）
2. structured_summary: 结构化 JSON（confirmed / excluded / pending / entities / intent）

Prompt 设计原则（对齐 FR-WM-002 / FR-SS-001）：
- 保留关键实体：人名、地名、时间、数值、业务 ID、技术术语
- 去除寒暄、重复确认等低信息内容
- 压缩率目标 20%-30%
- 强制结构化输出，便于下游 Prompt 注入与归档
"""
import json
import logging
from typing import Any

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Prompt 版本管理
# ---------------------------------------------------------------------------
PROMPT_VERSION = "v1.0"
PROMPT_VERSIONS: dict[str, str] = {
    "v1.0": "初始版本：增量压缩 + 校正压缩 + 结构化 JSON 输出",
}


def get_current_version() -> str:
    """获取当前生效的 Prompt 版本号."""
    return PROMPT_VERSION


# ---------------------------------------------------------------------------
# 系统角色 Prompt（压缩专用）
# ---------------------------------------------------------------------------
SYSTEM_ROLE = (
    "你是一个对话摘要专家，擅长从多轮对话中提取关键信息并压缩冗余内容。"
    "你的输出将被注入到后续 LLM Prompt 中作为上下文摘要，因此必须精准、无遗漏、无冗余。"
)


# ---------------------------------------------------------------------------
# 增量压缩 Prompt 模板
# ---------------------------------------------------------------------------
INCREMENTAL_COMPRESS_TEMPLATE = """请将以下对话历史增量压缩为简洁的结构化摘要。

【压缩要求】
1. 保留关键实体：人名、地名、时间、数值、业务 ID、技术术语
2. 保留已确认的结论和已排除的方案
3. 保留待办事项和未解决问题
4. 去除寒暄、重复确认、客套等低信息内容
5. 压缩率为原始文本的 20%-30%
6. 自然语言摘要不超过 100 字

【输出格式（严格 JSON，禁止输出其他内容）】
```json
{{
  "natural_summary": "100 字以内的自然语言摘要",
  "structured_summary": {{
    "confirmed": ["已确认结论1", "已确认结论2"],
    "excluded": ["已排除方案1"],
    "pending": ["待办事项1", "待解决问题1"],
    "entities": ["人名", "地名", "时间", "数值", "业务ID", "技术术语"],
    "intent": "当前用户意图"
  }}
}}
```

【已有摘要（请在此基础上增量更新）】
{existing_summary}

【待压缩对话】
{conversation_text}
"""


# ---------------------------------------------------------------------------
# 校正压缩 Prompt 模板
# ---------------------------------------------------------------------------
CORRECTIVE_COMPRESS_TEMPLATE = """请对以下内容执行校正压缩。你将看到已有的概念摘要和当前对话窗口，\
请综合两者产出一份完整、准确、无遗漏的校正摘要。

【校正要求】
1. 保留所有关键实体（人名、地名、时间、数值、技术术语、业务 ID）
2. 保留已确认的结论和已排除的方案
3. 保留待办事项和未解决问题
4. 去除寒暄、重复确认等低信息内容
5. 压缩率为原始文本的 20%-30%
6. 自然语言摘要不超过 100 字
7. 校正已有摘要中可能存在的不准确或遗漏信息

【输出格式（严格 JSON，禁止输出其他内容）】
```json
{{
  "natural_summary": "100 字以内的自然语言摘要",
  "structured_summary": {{
    "confirmed": ["已确认结论1", "已确认结论2"],
    "excluded": ["已排除方案1"],
    "pending": ["待办事项1", "待解决问题1"],
    "entities": ["人名", "地名", "时间", "数值", "业务ID", "技术术语"],
    "intent": "当前用户意图"
  }}
}}
```

【已有概念摘要（需校正）】
{existing_summary}

【当前对话窗口】
{conversation_text}
"""


# ---------------------------------------------------------------------------
# Prompt 构建函数
# ---------------------------------------------------------------------------

def build_incremental_prompt(
    messages: list[Any],
    existing_summary: str = "",
) -> str:
    """构建增量压缩 Prompt.

    Args:
        messages: 待压缩的 MessageItem 列表（溢出部分）
        existing_summary: 已有的自然语言摘要（可为空）

    Returns:
        完整的 Prompt 字符串
    """
    conversation_text = _format_messages(messages)
    return INCREMENTAL_COMPRESS_TEMPLATE.format(
        existing_summary=existing_summary or "（无，首次压缩）",
        conversation_text=conversation_text,
    )


def build_corrective_prompt(
    messages: list[Any],
    existing_summary: str = "",
) -> str:
    """构建校正压缩 Prompt.

    Args:
        messages: 当前对话窗口的 MessageItem 列表
        existing_summary: 已有的自然语言摘要

    Returns:
        完整的 Prompt 字符串
    """
    conversation_text = _format_messages(messages)
    return CORRECTIVE_COMPRESS_TEMPLATE.format(
        existing_summary=existing_summary or "（无）",
        conversation_text=conversation_text,
    )


def _format_messages(messages: list[Any]) -> str:
    """将 MessageItem 列表格式化为文本.

    每条消息截断至 500 字符，避免 Prompt 过长。
    """
    lines: list[str] = []
    for m in messages:
        role = getattr(m, "role", "unknown")
        content = getattr(m, "content", "")
        if isinstance(content, str):
            content = content[:500]
        lines.append(f"[{role}] {content}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# LLM 输出解析
# ---------------------------------------------------------------------------

def parse_compress_response(llm_output: str) -> dict[str, Any]:
    """解析 LLM 压缩输出为结构化字典.

    支持两种输入：
    1. 纯 JSON（新模板输出）
    2. 包含 JSON 代码块的文本（兼容旧格式或 LLM 偏离格式）

    Args:
        llm_output: LLM 返回的原始文本

    Returns:
        包含 natural_summary 和 structured_summary 的字典。
        解析失败时返回 fallback 结构。
    """
    if not llm_output or not llm_output.strip():
        return _fallback_parse(llm_output)

    # 尝试直接解析为 JSON
    try:
        return _safe_parse_json(llm_output)
    except (json.JSONDecodeError, ValueError):
        pass

    # 尝试从 ```json ... ``` 代码块中提取
    json_block = _extract_json_block(llm_output)
    if json_block:
        try:
            return _safe_parse_json(json_block)
        except (json.JSONDecodeError, ValueError):
            pass

    # 兜底：使用旧式文本解析
    logger.warning("Failed to parse LLM output as JSON, using fallback text parser")
    return _fallback_parse(llm_output)


def _safe_parse_json(text: str) -> dict[str, Any]:
    """安全解析 JSON，校验必需字段."""
    data = json.loads(text)
    if not isinstance(data, dict):
        raise ValueError("LLM output is not a JSON object")
    # 确保必需字段存在
    natural = data.get("natural_summary", "")
    structured = data.get("structured_summary", {})
    if not isinstance(structured, dict):
        structured = {}
    return {
        "natural_summary": str(natural),
        "structured_summary": {
            "confirmed": list(structured.get("confirmed", [])),
            "excluded": list(structured.get("excluded", [])),
            "pending": list(structured.get("pending", [])),
            "entities": list(structured.get("entities", [])),
            "intent": str(structured.get("intent", "")),
        },
    }


def _extract_json_block(text: str) -> str | None:
    """从 Markdown 代码块中提取 JSON 内容."""
    markers = ["```json", "```"]
    for marker in markers:
        if marker in text:
            start = text.find(marker) + len(marker)
            end = text.find("```", start)
            if end > start:
                return text[start:end].strip()
    return None


def _fallback_parse(text: str) -> dict[str, Any]:
    """兜底解析：从旧式文本摘要中提取结构化信息.

    兼容已有的 _parse_structured_summary 行为，确保旧版本 LLM 输出仍可用。
    """
    if not text:
        return {
            "natural_summary": "",
            "structured_summary": {
                "confirmed": [], "excluded": [], "pending": [], "entities": [], "intent": "",
            },
        }

    confirmed: list[str] = []
    excluded: list[str] = []
    pending: list[str] = []
    entities: list[str] = []
    intent = ""

    for line in text.split("\n"):
        line = line.strip().lstrip("- ").strip()
        if not line:
            continue
        if line.startswith("已确认") or line.startswith("确认结论"):
            content = _extract_after_colon(line)
            if content:
                confirmed.append(content)
        elif line.startswith("已排除") or line.startswith("排除方案"):
            content = _extract_after_colon(line)
            if content:
                excluded.append(content)
        elif line.startswith("待办") or line.startswith("待深入"):
            content = _extract_after_colon(line)
            if content:
                pending.append(content)
        elif line.startswith("关键实体"):
            content = _extract_after_colon(line)
            if content:
                entities.extend([e.strip() for e in content.split("、") if e.strip()])
        elif line.startswith("当前意图"):
            intent = _extract_after_colon(line)

    # 自然语言摘要取前 100 字
    natural = text.strip()[:100]

    return {
        "natural_summary": natural,
        "structured_summary": {
            "confirmed": confirmed,
            "excluded": excluded,
            "pending": pending,
            "entities": entities,
            "intent": intent,
        },
    }


def _extract_after_colon(line: str) -> str:
    """提取冒号后的内容（支持中英文冒号）."""
    for sep in ["：", ":"]:
        if sep in line:
            return line.split(sep, 1)[-1].strip()
    return ""
