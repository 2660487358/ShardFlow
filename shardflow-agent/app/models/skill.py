"""Skill 数据模型。

定义 Skill 元数据、加载候选、加载决策等数据结构，
供三级漏斗加载器、执行器、缓存层共用。

Per Skills管理需求规格文档 FR-6 / FR-7 / 实施计划 P5.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class SkillMeta:
    """Skill 元数据（来自 Java 后端 skill_registry + skill_version + skill_artifact 聚合）。

    与 Java 端 SkillDetailDTO 字段对齐，Python 端只保留运行时所需子集。
    """

    skill_id: int
    skill_code: str
    skill_name: str
    description: str = ""
    skill_type: str = "prompt"  # prompt | tool | hybrid | workflow
    trust_tier: str = "personal"  # official | team | personal
    owner_id: str = ""
    user_id: str = ""
    current_version: str = ""
    status: str = "draft"  # draft | reviewing | published | deprecated | archived
    trigger_keywords: list[str] = field(default_factory=list)
    input_schema: dict[str, Any] = field(default_factory=dict)
    output_schema: dict[str, Any] = field(default_factory=dict)
    cost_estimate: dict[str, Any] = field(default_factory=dict)
    config: dict[str, Any] = field(default_factory=dict)
    tags: list[str] = field(default_factory=list)
    category: str = ""
    source: str = "CUSTOM"  # CUSTOM | IMPORTED | BUILTIN
    # 绑定信息（来自 agent_skill_binding）
    binding_type: str = "optional"  # required | optional
    priority: int = 0
    config_override: dict[str, Any] = field(default_factory=dict)
    enabled: bool = True
    # Artifact 路径（来自 skill_artifact，按 artifact_type 索引）
    artifacts: dict[str, str] = field(default_factory=dict)
    # 内容哈希（来自 skill_version）
    content_hash: str = ""

    def to_prompt_meta(self) -> dict[str, Any]:
        """生成注入 LLM 决策 prompt 的精简元数据。"""
        return {
            "skill_code": self.skill_code,
            "skill_name": self.skill_name,
            "description": self.description,
            "skill_type": self.skill_type,
            "category": self.category,
            "trigger_keywords": self.trigger_keywords,
            "tags": self.tags,
            "binding_type": self.binding_type,
            "priority": self.priority,
        }


@dataclass
class LoadCandidate:
    """三级漏斗产出的加载候选。"""

    skill: SkillMeta
    # 第一层：硬性过滤后保留
    hard_filter_passed: bool = True
    hard_filter_reason: str = ""
    # 第二层：语义检索得分（V1 简化为关键词 + description 相似度）
    semantic_score: float = 0.0
    # LRU 偏好加权
    lru_boost: float = 0.0
    # 综合得分（semantic_score + lru_boost + priority 加权）
    final_score: float = 0.0


@dataclass
class LoadDecision:
    """LLM 决策输出（结构化 JSON 解析后）。"""

    selected_skill_codes: list[str] = field(default_factory=list)
    reason: str = ""
    raw_response: str = ""

    @classmethod
    def from_llm_response(cls, raw: str) -> "LoadDecision":
        """解析 LLM 输出为结构化决策。

        期望 LLM 返回 JSON：
        {
          "selected_skills": ["SKILL-xxx", "SKILL-yyy"],
          "reason": "用户意图需要..."
        }
        """
        import json
        import logging

        logger = logging.getLogger(__name__)
        try:
            # 容忍 markdown 代码块包裹
            text = raw.strip()
            if text.startswith("```"):
                text = text.split("```", 2)[1] if text.count("```") >= 2 else text
                if text.startswith("json"):
                    text = text[4:]
                text = text.strip()
            data = json.loads(text)
            return cls(
                selected_skill_codes=list(data.get("selected_skills", [])),
                reason=str(data.get("reason", "")),
                raw_response=raw,
            )
        except Exception as e:
            logger.warning(f"Failed to parse LLM load decision: {e}, raw={raw[:200]}")
            return cls(raw_response=raw)


@dataclass
class LoadAuditRecord:
    """Skill 加载审计记录（写入 skill_audit_log）。"""

    skill_id: int
    skill_code: str
    operation: str = "SKILL_LOAD"  # SKILL_LOAD | SKILL_EXECUTE | SKILL_PUBLISH ...
    operator_id: str = ""
    agent_id: str = ""
    session_id: str = ""
    details: dict[str, Any] = field(default_factory=dict)
    latency_ms: int = 0
    tokens_used: int = 0
    success: bool = True
    error: str = ""
