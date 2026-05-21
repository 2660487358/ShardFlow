"""L6 Security Layer: InputGuard — Prompt Injection & jailbreak detection."""
import re


class InspectionResult:
    def __init__(self, passed: bool, risk_level: str = "NONE", reasons: list[str] | None = None):
        self.passed = passed
        self.risk_level = risk_level
        self.reasons = reasons or []


class InputGuard:
    INJECTION_PATTERNS: list[str] = [
        r"忽略.*指令", r"ignore.*instruction", r"忽略.*系统",
        r"forget.*prompt", r"忘记.*提示", r"system:\s*",
        r"指令覆盖", r"override.*system",
        r"你不再是.*你是", r"you are not.*you are",
        r"扮演.*角色", r"act as.*DAN",
        r"越狱", r"jailbreak", r"do anything now",
        r"输出.*系统提示词", r"reveal.*prompt",
        r"print.*system.*message", r"show.*instruction",
    ]

    CODE_INJECTION_PATTERNS: list[str] = [
        r"\beval\s*\(", r"\bexec\s*\(", r"\bos\.system\s*\(",
        r"\bsubprocess\.", r"\b__import__\s*\(",
        r"\bcompile\s*\(", r"rm\s+-rf", r"DROP\s+TABLE",
    ]

    SQL_INJECTION_PATTERNS: list[str] = [
        r"(\bSELECT\b.*\bFROM\b|\bINSERT\b.*\bINTO\b|\bUPDATE\b.*\bSET\b|\bDELETE\b.*\bFROM\b)",
        r"\bUNION\b.*\bSELECT\b", r"--\s*$", r"/\*.*\*/", r"';.*--",
        r"\bOR\b\s+['\"]?\d+['\"]?\s*=\s*['\"]?\d+['\"]?",
    ]

    XSS_PATTERNS: list[str] = [
        r"<script[^>]*>.*?</script>",
        r"javascript\s*:", r"on\w+\s*=\s*\".*?\"",
        r"<iframe[^>]*>", r"<img[^>]*onerror",
        r"<svg[^>]*onload",
    ]

    SENSITIVE_WORDS: set[str] = {
        "暴力", "色情", "赌博", "毒品", "武器制造",
        "violence", "porn", "gambling", "drugs",
    }

    def inspect(self, input_text: str) -> InspectionResult:
        sanitized = self.sanitize(input_text)

        if len(sanitized) > 10000:
            return InspectionResult(False, "MEDIUM", ["input exceeds 10000 characters"])

        injection_reasons = self.detect_injection(sanitized)
        if injection_reasons:
            return InspectionResult(False, "CRITICAL", injection_reasons)

        jailbreak_reasons = self.detect_jailbreak(sanitized)
        if jailbreak_reasons:
            return InspectionResult(False, "CRITICAL", jailbreak_reasons)

        code_reasons = self._detect_code_injection(sanitized)
        if code_reasons:
            return InspectionResult(False, "MEDIUM", code_reasons)

        sql_reasons = self._detect_sql_injection(sanitized)
        if sql_reasons:
            return InspectionResult(False, "MEDIUM", sql_reasons)

        xss_reasons = self._detect_xss(sanitized)
        if xss_reasons:
            return InspectionResult(False, "MEDIUM", xss_reasons)

        sensitive = self._detect_sensitive(sanitized)
        if sensitive:
            return InspectionResult(True, "HIGH", [f"sensitive content detected: {sensitive}"])

        return InspectionResult(True, "NONE")

    def detect_injection(self, input_text: str) -> list[str]:
        reasons: list[str] = []
        lower = input_text.lower()
        for pattern in self.INJECTION_PATTERNS:
            if re.search(pattern, lower, re.IGNORECASE):
                reasons.append(f"injection pattern matched: {pattern}")
        return reasons

    def detect_jailbreak(self, input_text: str) -> list[str]:
        reasons: list[str] = []
        lower = input_text.lower()
        jailbreak_indicators = [
            r"dan\s*mode", r"developer\s*mode", r"god\s*mode",
            r"no\s*restrictions", r"no\s*limits", r"无限制",
            r"不.*受限", r"突破.*限制",
        ]
        for pattern in jailbreak_indicators:
            if re.search(pattern, lower, re.IGNORECASE):
                reasons.append(f"jailbreak pattern matched: {pattern}")
        return reasons

    def _detect_code_injection(self, input_text: str) -> list[str]:
        reasons: list[str] = []
        for pattern in self.CODE_INJECTION_PATTERNS:
            if re.search(pattern, input_text, re.IGNORECASE):
                reasons.append(f"code injection pattern: {pattern}")
        return reasons

    def _detect_sensitive(self, input_text: str) -> list[str]:
        found: list[str] = []
        lower = input_text.lower()
        for word in self.SENSITIVE_WORDS:
            if word.lower() in lower:
                found.append(word)
        return found

    def _detect_sql_injection(self, input_text: str) -> list[str]:
        reasons: list[str] = []
        for pattern in self.SQL_INJECTION_PATTERNS:
            if re.search(pattern, input_text, re.IGNORECASE):
                reasons.append(f"SQL injection pattern: {pattern}")
        return reasons

    def _detect_xss(self, input_text: str) -> list[str]:
        reasons: list[str] = []
        for pattern in self.XSS_PATTERNS:
            if re.search(pattern, input_text, re.IGNORECASE | re.DOTALL):
                reasons.append(f"XSS pattern: {pattern}")
        return reasons

    def sanitize(self, input_text: str) -> str:
        text = input_text.replace("\x00", "")
        text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", text)
        return text.strip()


input_guard = InputGuard()
