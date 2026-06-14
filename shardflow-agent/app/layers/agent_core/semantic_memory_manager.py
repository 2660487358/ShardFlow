"""SemanticMemoryManager — 语义记忆管理器 (FR-SM-001).

Manages the extraction, confidence evaluation, and persistence of user factual
information (semantic memory):

- FR-SM-001: User fact extraction with three trigger modes:
  1. Explicit confirmation (user says "记住我的偏好是...")
  2. NER-based extraction (key entity recognition from conversation)
  3. Multi-interaction inference (preferences inferred from repeated patterns)

- FR-SM-001: Confidence evaluation with four tiers:
  - High (0.9-1.0): Explicitly confirmed or repeatedly stated → direct write
  - Medium (0.7-0.89): Model inferred → write with pending-confirmation flag
  - Low (0.5-0.69): Single mention → draft only, not included in retrieval
  - Reject (<0.5): Discard

Storage: PostgreSQL (L2) + Milvus (L3) for semantic retrieval, with L0/L1 caching.
"""
import logging
import re
import uuid
from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, Field

from app.layers.agent_core.memory_orchestrator import memory_orchestrator
from app.models.memory import MemoryType

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data models for semantic extraction results
# ---------------------------------------------------------------------------

class ExtractedFact(BaseModel):
    """A single extracted user fact with confidence assessment."""
    text: str = ""                                       # Original text
    category: str = "preference"                         # preference|profile|history
    confidence: float = 0.5
    source: str = "conversation"                         # conversation|explicit_confirmation|ner_extraction|inferred
    structured: dict[str, Any] = Field(default_factory=dict)
    session_id: str = ""


class SemanticExtractionResult(BaseModel):
    """Result of semantic extraction from a conversation."""
    facts: list[ExtractedFact] = Field(default_factory=list)
    extraction_method: str = ""                          # explicit|ner|inferred|mixed
    total_extracted: int = 0


# ---------------------------------------------------------------------------
# Confidence thresholds per spec FR-SM-001
# ---------------------------------------------------------------------------

class ConfidenceTier:
    """Confidence evaluation tiers per spec FR-SM-001."""
    HIGH_MIN = 0.9       # Direct write
    MEDIUM_MIN = 0.7     # Write with pending-confirmation flag
    LOW_MIN = 0.5        # Draft only, not included in retrieval
    REJECT_MAX = 0.5     # Discard

    @classmethod
    def classify(cls, confidence: float) -> str:
        """Classify a confidence score into a tier."""
        if confidence >= cls.HIGH_MIN:
            return "high"
        elif confidence >= cls.MEDIUM_MIN:
            return "medium"
        elif confidence >= cls.LOW_MIN:
            return "low"
        else:
            return "reject"

    @classmethod
    def should_persist(cls, confidence: float) -> bool:
        """Whether a fact with this confidence should be persisted."""
        return confidence >= cls.LOW_MIN

    @classmethod
    def is_retrievable(cls, confidence: float) -> bool:
        """Whether a fact with this confidence should be included in retrieval."""
        return confidence >= cls.MEDIUM_MIN


# ---------------------------------------------------------------------------
# Explicit confirmation patterns (FR-SM-001 trigger mode 1)
# ---------------------------------------------------------------------------

# Patterns that indicate the user is explicitly asking the agent to remember something
EXPLICIT_PATTERNS: list[re.Pattern] = [
    re.compile(r"记住[我我的]?(?:偏好|习惯|喜好|设置|选择)", re.IGNORECASE),
    re.compile(r"请?记住", re.IGNORECASE),
    re.compile(r"我(?:偏好|喜欢|习惯|常用|爱用|倾向)", re.IGNORECASE),
    re.compile(r"我(?:的)?(?:偏好|习惯|喜好|设置|选择)(?:是|为|用)", re.IGNORECASE),
    re.compile(r"以后(?:请|都|总是?)(?:用|按|照|以)", re.IGNORECASE),
    re.compile(r"默认(?:用|使用|选择|设为)", re.IGNORECASE),
    re.compile(r"my\s+(?:preference|default|habit)", re.IGNORECASE),
    re.compile(r"remember\s+(?:that|my|I)", re.IGNORECASE),
    re.compile(r"I\s+(?:prefer|always|usually|like\s+to)", re.IGNORECASE),
]

# Category-specific extraction patterns
CATEGORY_PATTERNS: dict[str, list[re.Pattern]] = {
    "preference": [
        re.compile(r"(?:偏好|喜欢|习惯|常用|爱用|倾向)(?:的?是|用|为)\s*(.+)", re.IGNORECASE),
        re.compile(r"(?:prefer|like|always\s+use)\s+(.+)", re.IGNORECASE),
    ],
    "profile": [
        re.compile(r"我(?:是|在|做|从事|负责)\s*(.+)", re.IGNORECASE),
        re.compile(r"I\s+(?:am|work|specialize)\s+(.+)", re.IGNORECASE),
    ],
}


# ---------------------------------------------------------------------------
# SemanticMemoryManager
# ---------------------------------------------------------------------------

class SemanticMemoryManager:
    """Manages semantic memory: user fact extraction, confidence evaluation,
    and persistence.

    Three extraction modes (FR-SM-001):
    1. Explicit confirmation: user directly states a preference
    2. NER extraction: key entities identified from conversation
    3. Multi-interaction inference: patterns deduced from repeated behaviors
    """

    def __init__(self) -> None:
        # Track per-user mention counts for inference mode
        # {user_id: {fact_key: count}}
        self._mention_tracker: dict[str, dict[str, int]] = {}
        # Minimum mentions before inferring a preference
        self.INFERENCE_THRESHOLD = 3

    # ------------------------------------------------------------------
    # FR-SM-001: User fact extraction — main entry point
    # ------------------------------------------------------------------

    async def extract_from_messages(
        self,
        user_id: str,
        messages: list[dict[str, Any]],
        session_id: str = "",
    ) -> SemanticExtractionResult:
        """Extract user facts from a list of conversation messages.

        Runs all three extraction modes and merges results.
        """
        all_facts: list[ExtractedFact] = []

        # Mode 1: Explicit confirmation
        explicit_facts = self._extract_explicit(user_id, messages, session_id)
        all_facts.extend(explicit_facts)

        # Mode 2: NER-based extraction
        ner_facts = await self._extract_ner(user_id, messages, session_id)
        all_facts.extend(ner_facts)

        # Mode 3: Multi-interaction inference
        inferred_facts = self._extract_inferred(user_id, messages, session_id)
        all_facts.extend(inferred_facts)

        # Deduplicate and classify confidence
        deduped = self._deduplicate(all_facts)

        # Persist facts that meet the threshold
        await self._persist_facts(user_id, deduped)

        # Determine dominant extraction method
        method = "mixed"
        if explicit_facts and not ner_facts and not inferred_facts:
            method = "explicit"
        elif ner_facts and not explicit_facts and not inferred_facts:
            method = "ner"
        elif inferred_facts and not explicit_facts and not ner_facts:
            method = "inferred"

        result = SemanticExtractionResult(
            facts=deduped,
            extraction_method=method,
            total_extracted=len(deduped),
        )

        logger.info(
            "Semantic extraction for user %s: %d facts (explicit=%d, ner=%d, inferred=%d)",
            user_id, len(deduped), len(explicit_facts), len(ner_facts), len(inferred_facts),
        )

        return result

    # ------------------------------------------------------------------
    # Mode 1: Explicit confirmation extraction
    # ------------------------------------------------------------------

    def _extract_explicit(
        self,
        user_id: str,
        messages: list[dict[str, Any]],
        session_id: str,
    ) -> list[ExtractedFact]:
        """Extract facts from explicit user confirmation statements.

        Users directly state preferences like "记住我的偏好是..." or "I prefer...".
        These get the highest confidence (0.95).
        """
        facts: list[ExtractedFact] = []

        for msg in messages:
            if msg.get("role") != "user":
                continue
            content = msg.get("content", "")
            if not content:
                continue

            # Check if the message matches any explicit pattern
            is_explicit = any(p.search(content) for p in EXPLICIT_PATTERNS)
            if not is_explicit:
                continue

            # Try to extract category-specific content
            category = "preference"
            extracted_text = content

            for cat, patterns in CATEGORY_PATTERNS.items():
                for pattern in patterns:
                    match = pattern.search(content)
                    if match:
                        category = cat
                        extracted_text = match.group(1).strip() if match.lastindex else content
                        break

            facts.append(ExtractedFact(
                text=extracted_text,
                category=category,
                confidence=0.95,  # Explicit confirmation → high confidence
                source="explicit_confirmation",
                structured={"original_text": content},
                session_id=session_id,
            ))

        return facts

    # ------------------------------------------------------------------
    # Mode 2: NER-based extraction
    # ------------------------------------------------------------------

    async def _extract_ner(
        self,
        user_id: str,
        messages: list[dict[str, Any]],
        session_id: str,
    ) -> list[ExtractedFact]:
        """Extract facts using NER (Named Entity Recognition) from conversation.

        Identifies user attributes such as:
        - Technical expertise level
        - Domain/field of work
        - Communication preferences
        - Tool/framework preferences

        Uses LLM for NER when available, falls back to pattern-based extraction.
        """
        # Collect user messages for NER analysis
        user_messages = [
            m.get("content", "") for m in messages
            if m.get("role") == "user" and m.get("content")
        ]

        if not user_messages:
            return []

        # Try LLM-based NER extraction
        try:
            llm_facts = await self._llm_ner_extract(user_id, user_messages, session_id)
            if llm_facts:
                return llm_facts
        except Exception as e:
            logger.debug("LLM NER extraction failed, using pattern fallback: %s", e)

        # Fallback: pattern-based NER
        return self._pattern_ner_extract(user_id, user_messages, session_id)

    async def _llm_ner_extract(
        self,
        user_id: str,
        user_messages: list[str],
        session_id: str,
    ) -> list[ExtractedFact]:
        """Use LLM to extract user facts from messages via NER."""
        from app.layers.agent_core.model_client_manager import model_client_manager
        from app.layers.agent_core.llm_router import llm_router

        model_id = llm_router.MODEL_MAP.get("ner", "deepseek-chat")
        client, actual_model = await model_client_manager.get_client(model_id)

        # Build NER prompt
        conversation_text = "\n".join(f"- {m[:300]}" for m in user_messages[:20])

        prompt = (
            "请从以下用户对话中提取用户的事实信息和个人偏好。要求：\n"
            "1. 只提取明确提及的信息，不要推测\n"
            "2. 每条信息标注类别：preference(偏好)、profile(个人属性)\n"
            "3. 每条信息标注置信度：0.7-0.89（模型推断）\n"
            "4. 输出JSON数组格式：[{\"text\": \"...\", \"category\": \"...\", \"confidence\": 0.8}]\n"
            "5. 如果没有可提取的信息，输出空数组 []\n\n"
            f"用户对话：\n{conversation_text}"
        )

        payload = {
            "model": actual_model,
            "messages": [
                {"role": "system", "content": "你是一个用户画像信息提取专家，擅长从对话中识别用户偏好和属性。"},
                {"role": "user", "content": prompt},
            ],
            "max_tokens": 1024,
            "temperature": 0.2,
        }

        resp = await client.post("/chat/completions", json=payload, timeout=15.0)
        resp.raise_for_status()
        data = resp.json()

        choices = data.get("choices", [])
        if not choices:
            return []

        content = choices[0].get("message", {}).get("content", "")

        # Parse JSON from LLM response
        import json
        facts: list[ExtractedFact] = []

        # Try to extract JSON array from response
        json_match = re.search(r'\[.*\]', content, re.DOTALL)
        if json_match:
            try:
                items = json.loads(json_match.group())
                for item in items:
                    if isinstance(item, dict) and item.get("text"):
                        confidence = float(item.get("confidence", 0.75))
                        # Clamp to medium range for NER-extracted facts
                        confidence = max(0.7, min(0.89, confidence))
                        facts.append(ExtractedFact(
                            text=item["text"],
                            category=item.get("category", "preference"),
                            confidence=confidence,
                            source="ner_extraction",
                            session_id=session_id,
                        ))
            except (json.JSONDecodeError, ValueError) as e:
                logger.warning("Failed to parse NER extraction result: %s", e)

        return facts

    def _pattern_ner_extract(
        self,
        user_id: str,
        user_messages: list[str],
        session_id: str,
    ) -> list[ExtractedFact]:
        """Fallback NER extraction using pattern matching."""
        facts: list[ExtractedFact] = []

        # Expertise level detection
        expertise_patterns = {
            "advanced": re.compile(r"(?:高级|资深|专家|expert|advanced|senior)", re.IGNORECASE),
            "intermediate": re.compile(r"(?:中级|intermediate|mid)", re.IGNORECASE),
            "beginner": re.compile(r"(?:初级|新手|入门|beginner|junior|novice)", re.IGNORECASE),
        }

        # Communication style detection
        style_patterns = {
            "concise": re.compile(r"(?:简洁|简短|精炼|concise|brief|short)", re.IGNORECASE),
            "detailed": re.compile(r"(?:详细|详尽|完整|detailed|comprehensive|thorough)", re.IGNORECASE),
            "technical": re.compile(r"(?:技术|专业|technical|professional)", re.IGNORECASE),
        }

        for msg in user_messages:
            # Detect expertise mentions
            for level, pattern in expertise_patterns.items():
                if pattern.search(msg):
                    facts.append(ExtractedFact(
                        text=f"用户专业水平: {level}",
                        category="profile",
                        confidence=0.75,
                        source="ner_extraction",
                        structured={"expertise": level},
                        session_id=session_id,
                    ))

            # Detect communication style preferences
            for style, pattern in style_patterns.items():
                if pattern.search(msg):
                    facts.append(ExtractedFact(
                        text=f"用户沟通风格偏好: {style}",
                        category="preference",
                        confidence=0.75,
                        source="ner_extraction",
                        structured={"communication_style": style},
                        session_id=session_id,
                    ))

        return facts

    # ------------------------------------------------------------------
    # Mode 3: Multi-interaction inference
    # ------------------------------------------------------------------

    def _extract_inferred(
        self,
        user_id: str,
        messages: list[dict[str, Any]],
        session_id: str,
    ) -> list[ExtractedFact]:
        """Infer user preferences from repeated patterns across interactions.

        Tracks how often certain topics/tools/behaviors appear in user messages.
        When a pattern exceeds the inference threshold, it's promoted to a fact.
        """
        facts: list[ExtractedFact] = []

        if user_id not in self._mention_tracker:
            self._mention_tracker[user_id] = {}

        tracker = self._mention_tracker[user_id]

        # Track tool/framework mentions
        tool_keywords = {
            "web_search": ["搜索", "search", "查找", "查一下"],
            "code_analysis": ["代码", "code", "分析代码", "review"],
            "document_read": ["文档", "document", "readme", "doc"],
        }

        for msg in messages:
            if msg.get("role") != "user":
                continue
            content = msg.get("content", "").lower()

            for tool, keywords in tool_keywords.items():
                if any(kw in content for kw in keywords):
                    key = f"tool_usage:{tool}"
                    tracker[key] = tracker.get(key, 0) + 1

        # Check for patterns that exceed the inference threshold
        for key, count in tracker.items():
            if count >= self.INFERENCE_THRESHOLD and key.startswith("tool_usage:"):
                tool = key.split(":", 1)[1]
                # Only emit once when threshold is first reached
                if count == self.INFERENCE_THRESHOLD:
                    facts.append(ExtractedFact(
                        text=f"用户频繁使用 {tool} 工具",
                        category="preference",
                        confidence=0.7,  # Inferred → medium confidence
                        source="inferred",
                        structured={"frequent_tool": tool, "mention_count": count},
                        session_id=session_id,
                    ))

        return facts

    # ------------------------------------------------------------------
    # Deduplication
    # ------------------------------------------------------------------

    def _deduplicate(self, facts: list[ExtractedFact]) -> list[ExtractedFact]:
        """Remove duplicate facts, keeping the highest confidence version."""
        seen: dict[str, ExtractedFact] = {}

        for fact in facts:
            # Create a simplified key for dedup
            key = fact.text.lower().strip()[:100]
            if key in seen:
                existing = seen[key]
                # Keep the one with higher confidence
                if fact.confidence > existing.confidence:
                    seen[key] = fact
            else:
                seen[key] = fact

        return list(seen.values())

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    async def _persist_facts(self, user_id: str, facts: list[ExtractedFact]) -> None:
        """Persist extracted facts to memory store.

        High/Medium confidence: write to SEMANTIC memory (L0+L1+L2).
        Low confidence: write with draft flag (not retrievable).
        Reject: discard.
        """
        for fact in facts:
            tier = ConfidenceTier.classify(fact.confidence)

            if tier == "reject":
                logger.debug("Rejecting low-confidence fact: %s (conf=%.2f)", fact.text[:50], fact.confidence)
                continue

            key = f"sem_{uuid.uuid4().hex[:8]}"
            data = {
                "text": fact.text,
                "category": fact.category,
                "confidence": fact.confidence,
                "source": fact.source,
                "session_id": fact.session_id,
                "structured": fact.structured,
                "is_draft": tier == "low",
                "pending_confirmation": tier == "medium",
            }

            try:
                await memory_orchestrator.write_semantic(user_id, key, data)
                logger.debug(
                    "Persisted semantic fact for user %s: %s (tier=%s, conf=%.2f)",
                    user_id, fact.text[:50], tier, fact.confidence,
                )
            except Exception as e:
                logger.warning("Failed to persist semantic fact: %s", e)

    # ------------------------------------------------------------------
    # Single-message extraction (for real-time processing)
    # ------------------------------------------------------------------

    async def extract_from_message(
        self,
        user_id: str,
        content: str,
        role: str,
        session_id: str = "",
    ) -> list[ExtractedFact]:
        """Extract semantic facts from a single message in real-time.

        Useful for inline extraction during conversation flow.
        """
        if role != "user":
            return []

        messages = [{"role": role, "content": content}]
        result = await self.extract_from_messages(user_id, messages, session_id)
        return result.facts

    # ------------------------------------------------------------------
    # Query semantic memory
    # ------------------------------------------------------------------

    async def search_facts(
        self,
        user_id: str,
        query: str = "",
        category: str = "",
        min_confidence: float = 0.7,
        limit: int = 10,
    ) -> list[dict[str, Any]]:
        """Search semantic memory for user facts.

        Only returns facts with confidence >= min_confidence (default 0.7,
        meaning medium and above are retrievable per spec).
        """
        from app.models.memory import MemoryQuery

        mq = MemoryQuery(
            memory_type=MemoryType.SEMANTIC,
            tags=[category] if category else [],
            limit=limit,
        )

        records = await memory_orchestrator.search(user_id, MemoryType.SEMANTIC, mq)

        # Filter by confidence and draft status
        results: list[dict[str, Any]] = []
        for record in records:
            data = record.data
            confidence = data.get("confidence", 0)
            is_draft = data.get("is_draft", False)

            # Skip drafts and low-confidence items
            if is_draft or confidence < min_confidence:
                continue

            # Optional text filter
            if query and query.lower() not in data.get("text", "").lower():
                continue

            results.append(data)

        return results

    # ------------------------------------------------------------------
    # Confirm a pending fact (upgrade confidence)
    # ------------------------------------------------------------------

    async def confirm_fact(self, user_id: str, fact_key: str) -> bool:
        """Confirm a pending fact, upgrading its confidence to high (0.95)."""
        record = await memory_orchestrator.read_semantic(user_id, fact_key)
        if record is None:
            return False

        data = record.data
        data["confidence"] = 0.95
        data["pending_confirmation"] = False
        data["confirmed_at"] = datetime.now(timezone.utc).isoformat()

        await memory_orchestrator.write_semantic(user_id, fact_key, data)
        logger.info("Confirmed semantic fact for user %s: %s", user_id, fact_key)
        return True

    # ------------------------------------------------------------------
    # Get all user facts for profile building
    # ------------------------------------------------------------------

    async def get_user_facts(
        self,
        user_id: str,
        min_confidence: float = 0.7,
    ) -> list[dict[str, Any]]:
        """Get all confirmed user facts for profile building.

        Returns facts with confidence >= min_confidence, grouped by category.
        """
        return await self.search_facts(
            user_id, min_confidence=min_confidence, limit=100,
        )


# Global singleton
semantic_memory_manager = SemanticMemoryManager()
