"""L6 Security Layer: OutputGuard — PII masking & harmful content filtering."""
import re
from typing import Any


class OutputGuard:
    PII_PATTERNS: list[tuple[str, str, Any]] = [
        (
            r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}",
            "email",
            lambda m: f"{m.group(0)[0]}***@{m.group(0).split('@')[1]}" if "@" in m.group(0) else "***@***",
        ),
        (
            r"1[3-9]\d{9}",
            "phone",
            lambda m: f"{m.group(0)[:3]}****{m.group(0)[-4:]}",
        ),
        (
            r"\d{17}[\dXx]",
            "id_card",
            lambda m: f"{m.group(0)[:3]}***********{m.group(0)[-4:]}",
        ),
        (
            r"sk-[a-zA-Z0-9]{20,}",
            "api_key",
            lambda m: "sk-****",
        ),
        (
            r"\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}",
            "ip_address",
            lambda m: ".".join(m.group(0).split(".")[:2]) + ".***.***",
        ),
        (
            r"eyJ[a-zA-Z0-9_-]+\.[a-zA-Z0-9_-]+\.[a-zA-Z0-9_-]+",
            "jwt_token",
            lambda m: "[JWT_REMOVED]",
        ),
    ]

    HARMFUL_PATTERNS: list[str] = [
        # 英文模式
        r"\b(?:kill|murder|attack)\b.*\b(?:people|person|someone)\b",
        r"\b(?:bomb|weapon|explosive)\b.*\b(?:make|build|create)\b",
        r"\bchild\s*(?:porn|abuse|exploitation)\b",
        # 中文模式
        r"(炸弹|爆炸物|武器|枪支|弹药)",
        r"(黑客|入侵|漏洞利用|网络攻击)",
        r"(诈骗|欺诈|钓鱼|洗钱)",
        r"(自杀|自残|轻生)",
        r"(赌博|毒品|违禁品)",
    ]

    def inspect(self, output_text: str) -> dict[str, Any]:
        masked = self.mask_pii(output_text)
        pii_masked = masked != output_text

        has_harmful = self.detect_harmful(masked)
        is_compliant = self.check_compliance(masked)

        return {
            "text": masked if (pii_masked or has_harmful) else output_text,
            "pii_masked": pii_masked,
            "harmful_detected": has_harmful,
            "compliant": is_compliant,
        }

    def mask_pii(self, text: str) -> str:
        lines = text.split("\n")
        result_lines: list[str] = []
        in_code_block = False

        for line in lines:
            if line.strip().startswith("```"):
                in_code_block = not in_code_block
                result_lines.append(line)
                continue

            if in_code_block:
                result_lines.append(line)
                continue

            for pattern, _name, replacer in self.PII_PATTERNS:
                line = re.sub(pattern, replacer, line)
            result_lines.append(line)

        return "\n".join(result_lines)

    def detect_harmful(self, text: str) -> bool:
        lower = text.lower()
        for pattern in self.HARMFUL_PATTERNS:
            if re.search(pattern, lower, re.IGNORECASE):
                return True
        return False

    def check_compliance(self, text: str) -> bool:
        lower = text.lower()
        leakage_indicators = [
            r"password\s*[=:]\s*\S+",
            r"secret\s*[=:]\s*\S+",
            r"private\s*key",
            r"access_key",
        ]
        for pattern in leakage_indicators:
            if re.search(pattern, lower, re.IGNORECASE):
                return False
        return True


output_guard = OutputGuard()
