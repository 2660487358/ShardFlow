"""Output Post-Processing Pipeline — 企业级Agent模型输出行为规范实现.

5步清洗流水线:
1. TagParser: 解析 <THINKING>/<ANSWER> 标签
2. IsolationValidator: 验证内容隔离（思考过程不泄露到答案）
3. MetaCommentFilter: 元评论过滤
4. FormatNormalizer: 格式标准化
5. SafetyScan: 安全审查（委托给 OutputGuard）

降级策略: P0-P3 四级处理
"""
import logging
import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


class ViolationLevel(str, Enum):
    P0_FATAL = "p0_fatal"
    P1_SEVERE = "p1_severe"
    P2_GENERAL = "p2_general"
    P3_MINOR = "p3_minor"


@dataclass
class ProcessingResult:
    """后处理流水线输出结果"""
    answer: str = ""
    thinking: str = ""
    is_valid: bool = True
    violation_level: ViolationLevel | None = None
    violation_details: list[str] = field(default_factory=list)
    fallback_used: bool = False
    fallback_reason: str = ""


# ---- 元评论关键词库（规范 3.1.3） ----

META_COMMENT_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"让我(先|再)?(想想|思考一下|搜索|查询|调研)"),
    re.compile(r"我(需要|要|将|会|准备|打算)(先|再)?(进行|执行|调用|搜索|查询|调研|分析|提供)"),
    re.compile(r"基于(当前|现有|目前)(对话|状态|上下文|信息)"),
    re.compile(r"为了(准确|更好|深入)(理解|回答|分析|处理)"),
    re.compile(r"我(已经|已|刚|刚才)(完成|进行|执行|调用|搜索|查询)"),
    re.compile(r"由于(外部|网络|系统|工具)(搜索|查询|调用)(未返回|无结果|失败)"),
    re.compile(r"我(将|会|准备)基于(内置|内部|已有|训练)知识(库|回答)"),
    re.compile(r"以上(是|为)(我|本助手)(的|所)(回答|分析|总结|输出)"),
    re.compile(r"(现在|接下来|然后|接着)(我|系统)(将|会|进行|执行)"),
    re.compile(r"action_plan|tool_call|function_call|web_search"),
    re.compile(r"我刚刚(搜索|查询|调用|执行)了"),
    re.compile(r"根据(搜索|查询|调用)(结果|返回)"),
]

# ---- THINKING 专用元评论模式（比 ANSWER 更严格） ----
# 规范 2.1: 系统内部层严格隔离，禁止外泄
# 规范 3.1.1: THINKING 中禁止包含自我指涉的元评论
# 规范 3.3.1 detailed 模式: 展示内容需经过二次清洗（去除工具协议、内部状态）

THINKING_META_PATTERNS: list[re.Pattern[str]] = [
    # ---- 自我指涉元评论 ----
    re.compile(r"我(需要|要|将|会|准备|打算|应该)(先|再)?(提供|给出|生成|写|做|创建|构建|设计|介绍|覆盖|涵盖|拆解|分析|梳理|说明)"),
    re.compile(r"我(可以|能|应该)(直接|先|再)?(基于|根据|从|用)"),
    re.compile(r"我(将|会|准备|打算)(从|按|以|围绕).*(出发|逐层|展开|梳理|拆解|介绍)"),
    re.compile(r"(无需|不需要|不必)(调用|使用|执行)(工具|搜索|查询)"),
    re.compile(r"(可以直接|可以基于|无需调用|不需要调用)"),

    # ---- 用户画像/系统状态暴露 ----
    re.compile(r"用户画像(显示|表明|为|是)"),
    re.compile(r"用户(偏好|水平|风格|专业水平|专业)(为|是|显示|表明|：|:)?"),
    re.compile(r"用户(偏好|水平|风格).*(详细|简洁|深度|overview|detail|intermediate|beginner|expert)"),
    re.compile(r"(专业水平|期望|偏好).*(intermediate|beginner|expert|详细|简洁|深度)"),
    re.compile(r"(intermediate|beginner|expert|DETAIL|OVERVIEW|concise|detailed)"),

    # ---- 工具调用决策暴露 ----
    re.compile(r"(无需|不需要|不必)(调用|使用)(工具|搜索|联网)"),
    re.compile(r"(调用|使用|执行)(工具|搜索|联网).*(获取|查找|检索)"),
    re.compile(r"这是一个(开放|封闭|简单|复杂)式的?(讨论|问题|话题)"),

    # ---- 过程性决策暴露 ----
    re.compile(r"我(将|会|准备|打算)(基于|根据|从).*(知识|内置|训练|已有)"),
    re.compile(r"(基于|根据)(知识|内置|训练|已有).*(回答|给出|提供|生成)"),

    # ---- 输出计划暴露（"我将从X出发，按Y拆解"等） ----
    re.compile(r"(最后|最终).*(给出|提供|总结|建议|排序)"),
    re.compile(r"(按|按照).*(维度|层次|链路|方面|角度).*(拆解|展开|分析|梳理)"),
]

# 工具协议关键词
TOOL_PROTOCOL_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r'"action_plan"'),
    re.compile(r'"tool_call"'),
    re.compile(r'"function_call"'),
    re.compile(r'\bweb_search\b'),
    # Catch the full action_plan object that may leak through streaming
    re.compile(r'\{\s*"action_plan"\s*:\s*\{'),
]

# P0 兜底话术
P0_FALLBACK_MESSAGE = "系统处理中，请稍候重试。"

# P1 重新生成提示
P1_REGENERATE_PROMPT = "请基于你的思考过程，用简洁专业的语言直接回答用户问题，不要包含任何推理过程或元评论。"


class TagParser:
    """步骤1: 标签解析 — 提取 <THINKING> 和 <ANSWER> 内容

    使用正则匹配处理标签变体（空格、换行等），
    例如 <THINKING>, <THINKING >, </THINKING\n> 等。
    """

    # Regex patterns for robust tag detection (handles whitespace variations)
    _RE_THINKING_OPEN = re.compile(r"<THINKING\s*>", re.IGNORECASE)
    _RE_THINKING_CLOSE = re.compile(r"</THINKING\s*>", re.IGNORECASE)
    _RE_ANSWER_OPEN = re.compile(r"<ANSWER\s*>", re.IGNORECASE)
    _RE_ANSWER_CLOSE = re.compile(r"</ANSWER\s*>", re.IGNORECASE)

    @staticmethod
    def parse(text: str) -> tuple[str, str, list[str]]:
        """解析标签，返回 (thinking, answer, issues)"""
        issues: list[str] = []

        # 提取 THINKING 内容
        thinking = TagParser._extract_tag_content_regex(
            text,
            TagParser._RE_THINKING_OPEN,
            TagParser._RE_THINKING_CLOSE,
        )

        # 提取 ANSWER 内容
        answer = TagParser._extract_tag_content_regex(
            text,
            TagParser._RE_ANSWER_OPEN,
            TagParser._RE_ANSWER_CLOSE,
        )

        # 标签完整性检查
        has_thinking_open = bool(TagParser._RE_THINKING_OPEN.search(text))
        has_thinking_close = bool(TagParser._RE_THINKING_CLOSE.search(text))
        has_answer_open = bool(TagParser._RE_ANSWER_OPEN.search(text))
        has_answer_close = bool(TagParser._RE_ANSWER_CLOSE.search(text))

        if not has_thinking_open or not has_thinking_close:
            issues.append("THINKING标签缺失或不完整")
        if not has_answer_open or not has_answer_close:
            issues.append("ANSWER标签缺失或不完整")

        # 标签嵌套检查
        if thinking and TagParser._RE_ANSWER_OPEN.search(thinking):
            issues.append("THINKING中嵌套了ANSWER标签")
        if answer and TagParser._RE_THINKING_OPEN.search(answer):
            issues.append("ANSWER中嵌套了THINKING标签")

        # 降级：如果标签缺失，尝试从原始文本中提取
        if not answer and not thinking:
            # 完全没有标签结构，尝试旧格式兼容
            answer, thinking = TagParser._legacy_parse(text)
            if answer or thinking:
                issues.append("标签结构缺失，使用降级解析")

        # 最终安全网：清除答案中残留的标签标记
        answer = TagParser._strip_remaining_tags(answer)
        thinking = TagParser._strip_remaining_tags(thinking)

        return thinking, answer, issues

    @staticmethod
    def _extract_tag_content_regex(text: str, open_re: re.Pattern[str], close_re: re.Pattern[str]) -> str:
        """使用正则提取标签内容，处理标签变体。"""
        open_match = open_re.search(text)
        if not open_match:
            return ""
        start = open_match.end()
        close_match = close_re.search(text[start:])
        if not close_match:
            return text[start:].strip()
        return text[start:start + close_match.start()].strip()

    @staticmethod
    def _strip_remaining_tags(text: str) -> str:
        """清除文本中残留的标签标记（安全网）。

        处理各种变体：
        - <THINKING>, </THINKING>, <ANSWER>, </ANSWER>
        - 带空格/换行的变体
        - 不完整的标签（如 </THINKING, <ANSWER）
        """
        if not text:
            return text
        # 完整标签
        text = re.sub(r'</?THINKING\s*>', '', text, flags=re.IGNORECASE)
        text = re.sub(r'</?ANSWER\s*>', '', text, flags=re.IGNORECASE)
        # 不完整标签（缺少 > 的标签，如 </THINKING 或 </ANSWER）
        text = re.sub(r'</?THINKING(?!\s*>)[^>]*$', '', text, flags=re.IGNORECASE)
        text = re.sub(r'</?ANSWER(?!\s*>)[^>]*$', '', text, flags=re.IGNORECASE)
        # 清理多余空行
        text = re.sub(r'\n{3,}', '\n\n', text)
        return text.strip()

    @staticmethod
    def _legacy_parse(text: str) -> tuple[str, str]:
        """降级解析：兼容旧格式（无标签，纯文本+JSON块）"""
        # 尝试从 JSON 块中提取 final_answer
        json_match = re.search(r'```json\s*(\{.*?\})\s*```', text, re.DOTALL)
        if json_match:
            import json
            try:
                parsed = json.loads(json_match.group(1))
                if "final_answer" in parsed:
                    answer = parsed["final_answer"]
                    # JSON块之前的文本作为thinking
                    thinking = text[:json_match.start()].strip()
                    return answer, thinking
                if "action_plan" in parsed:
                    # action_plan 情况：answer为空，thinking为全文
                    return "", text
            except (json.JSONDecodeError, IndexError):
                pass

        # 无JSON块：全部作为answer（最终兜底）
        return text.strip(), ""


class IsolationValidator:
    """步骤2: 内容隔离验证 — 确保 ANSWER 不包含 THINKING 内容"""

    @staticmethod
    def validate(thinking: str, answer: str) -> tuple[bool, float, list[str]]:
        """验证隔离性，返回 (is_isolated, similarity, issues)"""
        issues: list[str] = []

        if not thinking or not answer:
            return True, 0.0, issues

        # 简单文本相似度检测（基于子串匹配，避免引入重依赖）
        similarity = IsolationValidator._compute_similarity(thinking, answer)

        if similarity > 0.85:
            issues.append(f"ANSWER与THINKING高度相似({similarity:.0%})，思考过程可能泄露")
        elif similarity > 0.3:
            issues.append(f"ANSWER与THINKING存在部分相似({similarity:.0%})")

        # 检查 ANSWER 中是否包含工具调用 JSON
        for pattern in TOOL_PROTOCOL_PATTERNS:
            if pattern.search(answer):
                issues.append(f"ANSWER中包含工具协议关键词: {pattern.pattern}")
                similarity = max(similarity, 0.9)  # 提升为严重违规

        is_isolated = similarity <= 0.3
        return is_isolated, similarity, issues

    @staticmethod
    def _compute_similarity(text_a: str, text_b: str) -> float:
        """基于n-gram重叠率的简单相似度计算"""
        if not text_a or not text_b:
            return 0.0

        def _ngrams(text: str, n: int = 4) -> set[str]:
            clean = re.sub(r'\s+', '', text.lower())
            return {clean[i:i + n] for i in range(len(clean) - n + 1)} if len(clean) >= n else {clean}

        ngrams_a = _ngrams(text_a)
        ngrams_b = _ngrams(text_b)

        if not ngrams_a or not ngrams_b:
            return 0.0

        intersection = ngrams_a & ngrams_b
        union = ngrams_a | ngrams_b
        return len(intersection) / len(union) if union else 0.0


class MetaCommentFilter:
    """步骤3: 元评论过滤 — 删除 ANSWER 中的自我指涉表述"""

    @staticmethod
    def filter(answer: str) -> tuple[str, int, list[str]]:
        """过滤元评论，返回 (cleaned_answer, removed_count, removed_items)"""
        if not answer:
            return answer, 0, []

        removed_items: list[str] = []
        lines = answer.split('\n')
        cleaned_lines: list[str] = []

        for line in lines:
            original = line
            is_meta = False
            for pattern in META_COMMENT_PATTERNS:
                if pattern.search(line):
                    is_meta = True
                    break

            if is_meta:
                removed_items.append(original.strip())
            else:
                cleaned_lines.append(line)

        cleaned = '\n'.join(cleaned_lines).strip()
        # 清理多余空行
        cleaned = re.sub(r'\n{3,}', '\n\n', cleaned)

        return cleaned, len(removed_items), removed_items


class FormatNormalizer:
    """步骤4: 格式标准化 — Markdown语法校验与修复

    企业级Agent多维表格输出规范实现：
    - 紧凑表格展开（多行挤在一行）
    - 对齐标记补全（分隔行必须有 :--- / ---: / :---:）
    - 空列删除（全空列整列删除）
    - 列数一致性修复（补齐空列或截断多余列）
    - 裸表检测与上下文补充
    - 单元格内嵌套列表清理
    """

    @staticmethod
    def normalize(text: str) -> str:
        if not text:
            return text

        # 移除控制字符（保留换行和制表符）
        text = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]', '', text)

        # 移除零宽字符
        text = re.sub(r'[\u200b-\u200f\u2028-\u202f\ufeff]', '', text)

        # 统一换行符
        text = text.replace('\r\n', '\n').replace('\r', '\n')

        # 修复 Markdown 表格格式：将紧凑的多行表格展开为独立行
        text = FormatNormalizer._fix_table_formatting(text)

        # 修复表格结构：对齐标记、空列、列数一致性
        text = FormatNormalizer._repair_table_structure(text)

        # 清理单元格内嵌套的无序列表标记
        text = FormatNormalizer._clean_nested_lists_in_tables(text)

        # 修复未闭合的代码围栏
        fence_count = text.count('```')
        if fence_count % 2 != 0:
            text += '\n```'

        return text.strip()

    @staticmethod
    def _fix_table_formatting(text: str) -> str:
        """修复 Markdown 表格格式.

        常见问题：LLM 输出的表格行之间缺少换行，导致多行表格挤在一行：
        | A | B ||---|---|| 1 | 2 |

        修复后：
        | A | B |
        |---|---|
        | 1 | 2 |
        """
        # 在代码围栏内不做处理
        parts = re.split(r'(```[\s\S]*?```)', text)
        for i, part in enumerate(parts):
            if part.startswith('```'):
                continue
            parts[i] = FormatNormalizer._expand_compact_tables(part)
        return ''.join(parts)

    @staticmethod
    def _expand_compact_tables(text: str) -> str:
        """将紧凑的表格行展开为独立行.

        检测模式：连续的 |...| |...| 之间缺少换行。
        规则：在 | 后紧跟 |（中间只有空格）的位置插入换行，
        但要排除表头分隔行 |---|---| 这种合法的同行格式。
        """
        lines = text.split('\n')
        result_lines: list[str] = []

        for line in lines:
            expanded = FormatNormalizer._split_compact_table_line(line)
            result_lines.extend(expanded)

        return '\n'.join(result_lines)

    @staticmethod
    def _split_compact_table_line(line: str) -> list[str]:
        """将一行中挤在一起的多个表格行拆分为独立行.

        例如：
        "| A | B | |---|---| | 1 | 2 |"
        拆分为：
        ["| A | B |", "|---|---|", "| 1 | 2 |"]

        注意：必须正确处理空列（如 |  |），不能将空列误判为行间分隔。
        策略：先按 "| " 拆分为单元格，然后按分隔行模式重新组合为行。
        """
        stripped = line.strip()
        if not stripped.startswith('|'):
            return [line]

        # 策略：使用正则匹配完整的表格行
        # 一个表格行的模式：| 开头，| 结尾，中间是单元格内容
        # 紧凑格式中，多个这样的行连在一起

        # 更可靠的策略：按 "| " 后紧跟 "|" 的模式拆分
        # 但空列 "|  |" 中 "| " 后紧跟 "|" 是合法的（空单元格）
        # 区分方法：空列的 "|" 后面紧跟 "|" 且中间只有空格，
        # 而行间分隔是 "| " 后面紧跟 "|" 且前面一个单元格已有内容

        # 最终策略：用正则找到所有分隔行（全是 - 和 : 的行），
        # 然后在分隔行前后拆分

        # 方法：将紧凑表格按分隔行模式拆分
        # 分隔行模式：| :?-+:? | :?-+:? | ...
        # 但分隔行可能和普通行混在一起

        # 最可靠方法：统计列数，然后按列数重新组合
        # 先尝试简单拆分，如果拆分后每行列数一致则成功

        pipe_count = stripped.count('|')
        if pipe_count < 4:
            return [line]

        # 尝试按 "| " + "|" 模式拆分，但排除空列
        # 空列模式：| (空格) | → "|  |" 或 "| |"
        # 行间分隔：| (内容) | | (内容) | → "| content | | content |"

        # 使用正则：在 "| " 后面紧跟 "|" 且前面不是空格的位置拆分
        # 即匹配 "| X |" 后面紧跟 "| Y |" 的模式

        parts: list[str] = []
        current = ""
        i = 0
        s = stripped

        while i < len(s):
            current += s[i]
            if s[i] == '|' and i + 1 < len(s):
                # 跳过空格
                j = i + 1
                while j < len(s) and s[j] == ' ':
                    j += 1
                if j < len(s) and s[j] == '|':
                    stripped_current = current.strip()
                    if stripped_current.startswith('|') and stripped_current.endswith('|'):
                        inner = stripped_current[1:-1].strip()
                        is_separator = all(c in '-|: ' for c in inner) and '-' in inner

                        # 检查是否是空列（当前累积内容只有 | 和空格）
                        # 空列：current 是 "|  " 或 "| "，即 inner 为空
                        is_empty_cell = inner == ''

                        if is_separator:
                            # 分隔行，拆分
                            parts.append(stripped_current)
                            current = ""
                            i = j
                            continue
                        elif is_empty_cell:
                            # 空列，不拆分，继续累积
                            pass
                        else:
                            # 非空非分隔，检查是否构成完整行
                            # 完整行判断：至少有2个非空单元格
                            cells = [c.strip() for c in stripped_current.split('|')[1:-1]]
                            non_empty = sum(1 for c in cells if c != '')
                            if non_empty >= 2:
                                # 可能是完整行，但也可能是多行累积
                                # 需要进一步判断：如果当前行和下一行的列数一致
                                # 简单策略：如果 pipe_count 很大（>6），尝试拆分
                                # 否则保持原样
                                if pipe_count > 6:
                                    parts.append(stripped_current)
                                    current = ""
                                    i = j
                                    continue
            i += 1

        remaining = current.strip()
        if remaining:
            parts.append(remaining)

        if len(parts) <= 1:
            return [line]

        return parts

    @staticmethod
    def _repair_table_structure(text: str) -> str:
        """修复表格结构问题：对齐标记、空列、列数一致性.

        参照企业级规范 3.2.1 表格修复流水线：
        步骤2: 结构解析 → 步骤3: 自动修复
        """
        # 在代码围栏内不做处理
        parts = re.split(r'(```[\s\S]*?```)', text)
        for i, part in enumerate(parts):
            if part.startswith('```'):
                continue
            parts[i] = FormatNormalizer._repair_tables_in_text(part)
        return ''.join(parts)

    @staticmethod
    def _repair_tables_in_text(text: str) -> str:
        """在非代码围栏文本中修复所有表格块"""
        # 匹配 Markdown 表格块：连续的以 | 开头的行
        table_pattern = r'((?:^[ \t]*\|[^\n]*\|[ \t]*$\n?)+)'
        lines = text.split('\n')

        result_lines: list[str] = []
        table_buffer: list[str] = []

        for line in lines:
            stripped = line.strip()
            if stripped.startswith('|') and stripped.endswith('|'):
                table_buffer.append(line)
            else:
                if table_buffer:
                    repaired = FormatNormalizer._repair_single_table(table_buffer)
                    result_lines.extend(repaired)
                    table_buffer = []
                result_lines.append(line)

        # 处理末尾的表格
        if table_buffer:
            repaired = FormatNormalizer._repair_single_table(table_buffer)
            result_lines.extend(repaired)

        return '\n'.join(result_lines)

    @staticmethod
    def _repair_single_table(table_lines: list[str]) -> list[str]:
        """修复单个表格块的结构问题"""
        if len(table_lines) < 2:
            return table_lines

        # 解析每行的单元格
        parsed_rows: list[list[str]] = []
        separator_idx: int | None = None

        for idx, line in enumerate(table_lines):
            stripped = line.strip()
            cells = [c.strip() for c in stripped.split('|')[1:-1]]
            parsed_rows.append(cells)

            # 检测分隔行
            inner = stripped[1:-1].strip()
            if all(c in '-|: ' for c in inner) and '-' in inner:
                separator_idx = idx

        # 修复1: 如果没有分隔行，在第一行后插入
        if separator_idx is None and len(parsed_rows) >= 2:
            num_cols = len(parsed_rows[0])
            alignments = ['left'] + ['center'] * (num_cols - 1)
            separator = FormatNormalizer._generate_separator(num_cols, alignments)
            parsed_rows.insert(1, [separator])
            # 标记分隔行位置
            separator_idx = 1

        # 修复2: 统一列数
        if parsed_rows:
            max_cols = max(len(r) for r in parsed_rows)
            for i, row in enumerate(parsed_rows):
                while len(row) < max_cols:
                    row.append('')
                if len(row) > max_cols:
                    parsed_rows[i] = row[:max_cols]

        # 修复3: 补全分隔行的对齐标记
        if separator_idx is not None and separator_idx < len(parsed_rows):
            sep_row = parsed_rows[separator_idx]
            num_cols = len(sep_row)
            for i, cell in enumerate(sep_row):
                cell_stripped = cell.strip()
                # 分隔行单元格合法格式：仅包含 - 和可选的 : 对齐标记
                # 如 ------, :---, ---:, :---:
                if re.match(r'^:?-+:?$', cell_stripped):
                    # 有对齐标记，标准化
                    if cell_stripped.startswith(':') and cell_stripped.endswith(':'):
                        sep_row[i] = ':---:'
                    elif cell_stripped.endswith(':'):
                        sep_row[i] = '---:'
                    elif cell_stripped.startswith(':'):
                        sep_row[i] = ':---'
                    else:
                        # 纯 ------ 格式，无对齐标记，补全默认对齐
                        sep_row[i] = ':---' if i == 0 else ':---:'
                else:
                    # 不符合分隔行格式，替换为默认对齐
                    sep_row[i] = ':---' if i == 0 else ':---:'

        # 修复4: 删除全空列（分隔行标记不算内容）
        if parsed_rows and len(parsed_rows) > 1:
            num_cols = len(parsed_rows[0])
            empty_cols: list[int] = []
            for col_idx in range(num_cols):
                is_empty = True
                for row_idx, row in enumerate(parsed_rows):
                    if col_idx < len(row):
                        cell = row[col_idx].strip()
                        # 分隔行（------, :--- 等）不算有效内容
                        if row_idx == separator_idx:
                            continue
                        if cell != '':
                            is_empty = False
                            break
                if is_empty:
                    empty_cols.append(col_idx)

            if empty_cols:
                for i, row in enumerate(parsed_rows):
                    parsed_rows[i] = [cell for idx, cell in enumerate(row) if idx not in empty_cols]

        # 重新组装表格行
        result: list[str] = []
        for row in parsed_rows:
            result.append('| ' + ' | '.join(row) + ' |')

        return result

    @staticmethod
    def _generate_separator(cols: int, alignments: list[str]) -> str:
        """生成分隔行"""
        cells = []
        for i, align in enumerate(alignments):
            if align == 'left':
                cells.append(':---')
            elif align == 'right':
                cells.append('---:')
            else:
                cells.append(':---:')
        return '| ' + ' | '.join(cells) + ' |'

    @staticmethod
    def _clean_nested_lists_in_tables(text: str) -> str:
        """清理表格单元格内嵌套的无序列表标记.

        规范 3.1.1: 禁止在单元格内使用无序列表（- item），
        如需列表使用 <br> 或表格后展开。
        """
        # 在代码围栏内不做处理
        parts = re.split(r'(```[\s\S]*?```)', text)
        for i, part in enumerate(parts):
            if part.startswith('```'):
                continue
            parts[i] = FormatNormalizer._clean_lists_in_text(part)
        return ''.join(parts)

    @staticmethod
    def _clean_lists_in_text(text: str) -> str:
        """在表格单元格内将 - item 格式转为逗号分隔"""
        lines = text.split('\n')
        in_table = False
        result: list[str] = []

        for line in lines:
            stripped = line.strip()
            if stripped.startswith('|') and stripped.endswith('|'):
                in_table = True
                # 检测并清理单元格内的列表标记
                # 模式：单元格内出现 "- xxx" 或 " - xxx"
                cleaned = re.sub(r'\s*-\s+', ', ', line)
                # 清理开头的 ", "（如果列表是单元格的第一个内容）
                cleaned = re.sub(r'\|\s*,\s+', '| ', cleaned)
                result.append(cleaned)
            else:
                in_table = False
                result.append(line)

        return '\n'.join(result)


class ThinkingContentFilter:
    """THINKING 内容二次清洗 — 规范 3.3.1 detailed 模式要求.

    即使在 detailed 模式下展示思考过程，也必须:
    - 去除工具协议关键词
    - 去除用户画像/系统状态信息
    - 去除自我指涉的元评论
    - 去除工具调用决策暴露

    这是流式推送前的最后一道防线。
    """

    @staticmethod
    def filter_streaming_chunk(chunk: str) -> str:
        """对流式推送的单个 thinking chunk 做轻量过滤.

        适用于逐 token 推送场景，只做行级过滤。
        返回过滤后的 chunk（可能为空字符串）。
        """
        if not chunk:
            return chunk

        # 检查是否命中任何 THINKING 专用元评论模式
        for pattern in THINKING_META_PATTERNS:
            if pattern.search(chunk):
                return ""

        # 检查是否命中通用元评论模式
        for pattern in META_COMMENT_PATTERNS:
            if pattern.search(chunk):
                return ""

        # 检查工具协议关键词
        for pattern in TOOL_PROTOCOL_PATTERNS:
            if pattern.search(chunk):
                return ""

        return chunk

    @staticmethod
    def filter_full_thinking(thinking: str) -> str:
        """对完整的 THINKING 内容做二次清洗.

        适用于图完成后、存储/展示前的清洗。
        采用片段级替换策略：只删除违规片段，保留同一行中的合规内容。
        返回清洗后的 thinking 文本。
        """
        if not thinking:
            return thinking

        # 收集所有需要过滤的模式
        all_patterns = THINKING_META_PATTERNS + META_COMMENT_PATTERNS + TOOL_PROTOCOL_PATTERNS

        # 对每个模式做片段级替换
        result = thinking
        for pattern in all_patterns:
            result = pattern.sub('', result)

        # 清理多余空行和空格
        result = re.sub(r'\n{3,}', '\n\n', result)
        result = re.sub(r' {2,}', ' ', result)
        # 清理句首/句尾残留标点
        result = re.sub(r'^[，。、；：\s]+', '', result, flags=re.MULTILINE)
        result = re.sub(r'[，。、；：\s]+$', '', result, flags=re.MULTILINE)

        return result.strip()


class OutputProcessor:
    """后处理清洗流水线 — 5步串联执行"""

    def __init__(self) -> None:
        self._tag_parser = TagParser()
        self._isolation_validator = IsolationValidator()
        self._meta_filter = MetaCommentFilter()
        self._format_normalizer = FormatNormalizer()

    def process(self, raw_output: str) -> ProcessingResult:
        """执行完整的5步清洗流水线"""
        result = ProcessingResult()

        # ---- 步骤1: 标签解析 ----
        thinking, answer, tag_issues = TagParser.parse(raw_output)
        if tag_issues:
            result.violation_details.extend(tag_issues)
            # 标签缺失是P3级别
            if any("缺失" in issue for issue in tag_issues):
                result.violation_level = ViolationLevel.P3_MINOR

        # ---- 步骤2: 内容隔离验证 ----
        is_isolated, similarity, isolation_issues = IsolationValidator.validate(thinking, answer)
        if isolation_issues:
            result.violation_details.extend(isolation_issues)

        # 判断违规级别
        if any("工具协议" in issue for issue in isolation_issues):
            result.violation_level = ViolationLevel.P0_FATAL
        elif similarity > 0.3:
            if result.violation_level is None or result.violation_level == ViolationLevel.P3_MINOR:
                result.violation_level = ViolationLevel.P1_SEVERE

        # ---- 步骤3: 元评论过滤 ----
        answer, removed_count, removed_items = MetaCommentFilter.filter(answer)
        if removed_count > 0:
            result.violation_details.append(f"过滤了{removed_count}条元评论: {removed_items[:3]}")
            if result.violation_level is None or result.violation_level == ViolationLevel.P3_MINOR:
                result.violation_level = ViolationLevel.P2_GENERAL

        # ---- 步骤4: 格式标准化 ----
        answer = FormatNormalizer.normalize(answer)
        thinking = FormatNormalizer.normalize(thinking)

        # ---- 步骤4.5: THINKING 内容二次清洗 ----
        # 规范 3.3.1: 展示内容需经过二次清洗（去除工具协议、内部状态）
        thinking = ThinkingContentFilter.filter_full_thinking(thinking)

        # ---- 步骤5: 安全审查（委托给 OutputGuard）----
        try:
            from app.layers.security.output_guard import output_guard
            guard_result = output_guard.inspect(answer)
            if not guard_result.get("compliant", True):
                result.violation_details.append("安全审查不通过：检测到敏感信息泄露")
                result.violation_level = ViolationLevel.P0_FATAL
            answer = guard_result.get("text", answer)
        except Exception:
            pass

        # ---- 步骤5.5: 最终标签清除（安全网）----
        # 确保答案中不残留任何标签标记，无论之前的步骤是否完美处理
        answer = TagParser._strip_remaining_tags(answer)
        thinking = TagParser._strip_remaining_tags(thinking)

        # ---- 降级处理 ----
        result = self._apply_degradation(result, thinking, answer)

        # 记录审计日志
        if result.violation_details:
            logger.warning(
                "OutputProcessor: violations detected - level=%s details=%s",
                result.violation_level,
                result.violation_details,
            )

        return result

    def _apply_degradation(self, result: ProcessingResult, thinking: str, answer: str) -> ProcessingResult:
        """根据违规级别应用降级策略"""
        level = result.violation_level

        if level == ViolationLevel.P0_FATAL:
            # P0: 完全阻断，返回兜底话术
            result.answer = P0_FALLBACK_MESSAGE
            result.thinking = thinking  # thinking保留供调试
            result.is_valid = False
            result.fallback_used = True
            result.fallback_reason = "P0致命违规：工具协议外泄或敏感信息泄露"
            logger.error("P0 violation detected, blocking output")

        elif level == ViolationLevel.P1_SEVERE:
            # P1: 丢弃ANSWER，尝试从THINKING重新生成精简版
            if thinking:
                # 提取thinking中的关键信息生成精简答案
                result.answer = self._regenerate_from_thinking(thinking)
                result.fallback_used = True
                result.fallback_reason = "P1严重违规：思考过程泄露，已重新生成"
            else:
                result.answer = P0_FALLBACK_MESSAGE
                result.is_valid = False
                result.fallback_used = True
                result.fallback_reason = "P1严重违规且无thinking可恢复"

        elif level == ViolationLevel.P2_GENERAL:
            # P2: 已在步骤3自动过滤元评论，正常输出
            result.answer = answer
            result.thinking = thinking
            result.is_valid = True

        elif level == ViolationLevel.P3_MINOR:
            # P3: 格式已自动修正，正常输出
            result.answer = answer
            result.thinking = thinking
            result.is_valid = True

        else:
            # 无违规
            result.answer = answer
            result.thinking = thinking
            result.is_valid = True

        return result

    @staticmethod
    def _regenerate_from_thinking(thinking: str) -> str:
        """从思考过程中提取关键信息生成精简答案"""
        # 提取thinking中的核心句子（非元评论的陈述句）
        sentences = re.split(r'[。！？\n]', thinking)
        key_sentences: list[str] = []
        for s in sentences:
            s = s.strip()
            if not s:
                continue
            # 跳过元评论
            is_meta = False
            for pattern in META_COMMENT_PATTERNS:
                if pattern.search(s):
                    is_meta = True
                    break
            if not is_meta and len(s) > 5:
                key_sentences.append(s)

        if key_sentences:
            # 取前3个关键句子作为精简答案
            return "。".join(key_sentences[:3]) + "。"
        return P0_FALLBACK_MESSAGE

    def process_answer_only(self, answer: str) -> str:
        """仅对answer文本执行轻量清洗（用于流式场景的最终校验）"""
        answer, _, _ = MetaCommentFilter.filter(answer)
        answer = FormatNormalizer.normalize(answer)
        return answer


# 全局实例
output_processor = OutputProcessor()
