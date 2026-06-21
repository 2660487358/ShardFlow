"""MemoryConflictResolver — 记忆冲突检测与解决 (FR-WU-002).

Detects and resolves conflicts when writing new memory that contradicts
existing memory. Per spec section 4.5 FR-WU-002:

Conflict types and resolution strategies:
- Value update (old → new): Timestamp overwrite + preserve history
- Preference change (like A → like B): Timestamp overwrite + log change
- Contradictory info (engineer vs doctor): Confidence arbitration + human confirm
- Duplicate info (same preference repeated): Dedup + update access count

Resolution priority rules:
1. Explicit confirmation takes precedence
2. High confidence overwrites low confidence (diff > 0.2)
3. Same confidence: newer timestamp wins
4. Unresolvable: preserve existing + mark conflict
"""
import logging
import uuid
from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, Field

from app.layers.agent_core.memory_orchestrator import memory_orchestrator
from app.models.memory import MemoryType

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Conflict detection models
# ---------------------------------------------------------------------------

class ConflictType:
    """Conflict type classification per spec FR-WU-002."""
    VALUE_UPDATE = "value_update"           # Old value → new value
    PREFERENCE_CHANGE = "preference_change" # Like A → like B
    CONTRADICTION = "contradiction"         # Engineer vs doctor
    DUPLICATE = "duplicate"                 # Same info repeated


class ConflictResolution:
    """Resolution outcome."""
    OVERWRITE = "overwrite"         # New value replaces old
    MERGE = "merge"                 # Merge both values
    PRESERVE = "preserve"           # Keep existing, mark conflict
    ESCALATE = "escalate"           # Needs human confirmation
    DISCARD_NEW = "discard_new"     # New value is inferior, discard


class ConflictRecord(BaseModel):
    """Record of a detected and resolved conflict."""
    conflict_id: str = Field(default_factory=lambda: f"cf_{uuid.uuid4().hex[:8]}")
    user_id: str = ""
    existing_memory_id: str = ""
    new_content: str = ""
    existing_content: str = ""
    conflict_type: str = ""        # ConflictType value
    resolution: str = ""           # ConflictResolution value
    resolution_reason: str = ""
    existing_confidence: float = 0.0
    new_confidence: float = 0.0
    resolved_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    model_config = {"extra": "allow"}


class ConflictDetectionResult(BaseModel):
    """Result of conflict detection for a new memory write."""
    has_conflict: bool = False
    conflict_type: str = ""
    existing_memory_id: str = ""
    existing_content: str = ""
    existing_confidence: float = 0.0
    similarity_score: float = 0.0
    resolution: str = ""           # ConflictResolution value
    resolution_reason: str = ""
    should_write: bool = True      # Whether to proceed with the write

    model_config = {"extra": "allow"}


# ---------------------------------------------------------------------------
# MemoryConflictResolver
# ---------------------------------------------------------------------------

class MemoryConflictResolver:
    """Detects and resolves memory conflicts per spec FR-WU-002.

    Resolution priority rules:
    1. Explicit confirmation takes precedence
    2. High confidence overwrites low confidence (diff > 0.2)
    3. Same confidence: newer timestamp wins
    4. Unresolvable: preserve existing + mark conflict

    Usage:
        resolver = MemoryConflictResolver()
        result = await resolver.detect_and_resolve(
            user_id="user_001",
            memory_type=MemoryType.SEMANTIC,
            category="preference",
            new_content="用户偏好使用Python",
            new_confidence=0.9,
            new_source="explicit_confirmation",
        )
        if result.should_write:
            # Proceed with write
    """

    # Confidence difference threshold for automatic overwrite
    CONFIDENCE_OVERWRITE_THRESHOLD: float = 0.2

    # Similarity threshold for considering two memories as potentially conflicting
    CONFLICT_SIMILARITY_THRESHOLD: float = 0.8

    def __init__(self) -> None:
        # L0 cache for recent conflict records
        self._conflict_log: list[ConflictRecord] = []
        self._max_log_size: int = 1000

    # ------------------------------------------------------------------
    # Main entry: detect and resolve
    # ------------------------------------------------------------------

    async def detect_and_resolve(
        self,
        user_id: str,
        memory_type: MemoryType,
        category: str,
        new_content: str,
        new_confidence: float = 0.5,
        new_source: str = "conversation",
        session_id: str = "",
    ) -> ConflictDetectionResult:
        """Detect conflicts and determine resolution for a new memory write.

        Steps:
        1. Search for existing memories in the same category
        2. Check for duplicates, value updates, preference changes, contradictions
        3. Apply resolution priority rules
        4. Return resolution decision
        """
        # Step 1: Find potentially conflicting memories
        existing_memories = await self._find_related_memories(
            user_id=user_id,
            memory_type=memory_type,
            category=category,
        )

        if not existing_memories:
            return ConflictDetectionResult(
                has_conflict=False,
                should_write=True,
            )

        # Step 2: Check for each conflict type
        for record_data in existing_memories:
            existing_content = record_data.get("text", "")
            existing_confidence = record_data.get("confidence", 0.0)
            existing_source = record_data.get("source", "conversation")
            existing_key = record_data.get("_key", "")

            if not existing_content:
                continue

            # Check for duplicate
            if self._is_duplicate(existing_content, new_content):
                return self._resolve_duplicate(
                    user_id=user_id,
                    existing_key=existing_key,
                    existing_content=existing_content,
                    existing_confidence=existing_confidence,
                    new_content=new_content,
                    new_confidence=new_confidence,
                )

            # Check for value update / preference change
            if self._is_value_update(existing_content, new_content, category):
                return self._resolve_value_update(
                    user_id=user_id,
                    existing_key=existing_key,
                    existing_content=existing_content,
                    existing_confidence=existing_confidence,
                    existing_source=existing_source,
                    new_content=new_content,
                    new_confidence=new_confidence,
                    new_source=new_source,
                    category=category,
                )

            # Check for contradiction
            if self._is_contradiction(existing_content, new_content):
                return self._resolve_contradiction(
                    user_id=user_id,
                    existing_key=existing_key,
                    existing_content=existing_content,
                    existing_confidence=existing_confidence,
                    existing_source=existing_source,
                    new_content=new_content,
                    new_confidence=new_confidence,
                    new_source=new_source,
                )

        # No conflict detected
        return ConflictDetectionResult(
            has_conflict=False,
            should_write=True,
        )

    # ------------------------------------------------------------------
    # Conflict detection helpers
    # ------------------------------------------------------------------

    def _is_duplicate(self, existing: str, new: str) -> bool:
        """Check if two memory contents are duplicates.

        Uses normalized text comparison for dedup.
        """
        norm_existing = self._normalize_text(existing)
        norm_new = self._normalize_text(new)

        if not norm_existing or not norm_new:
            return False

        # Exact match after normalization
        if norm_existing == norm_new:
            return True

        # One contains the other (subset)
        if norm_existing in norm_new or norm_new in norm_existing:
            return True

        # High similarity (simple word overlap)
        existing_words = set(norm_existing.split())
        new_words = set(norm_new.split())
        if existing_words and new_words:
            overlap = len(existing_words & new_words)
            total = len(existing_words | new_words)
            jaccard = overlap / total if total > 0 else 0.0
            if jaccard >= self.CONFLICT_SIMILARITY_THRESHOLD:
                return True

        return False

    def _is_value_update(self, existing: str, new: str, category: str) -> bool:
        """Check if the new content is a value update of the existing content.

        Value updates occur when the same attribute has a different value,
        e.g., "地址是A" → "地址是B", "喜欢Python" → "喜欢Rust".
        """
        # Check for same topic with different value
        existing_topic = self._extract_topic(existing)
        new_topic = self._extract_topic(new)

        if existing_topic and new_topic and existing_topic == new_topic:
            # Same topic but different content = value update
            return existing != new

        # Category-specific heuristics
        if category == "preference":
            # Preference changes: "偏好X" → "偏好Y"
            pref_keywords = ["偏好", "喜欢", "习惯", "常用", "prefer", "like"]
            existing_has_pref = any(kw in existing.lower() for kw in pref_keywords)
            new_has_pref = any(kw in new.lower() for kw in pref_keywords)
            if existing_has_pref and new_has_pref:
                return True

        return False

    def _is_contradiction(self, existing: str, new: str) -> bool:
        """Check if two memories contain contradictory information.

        Contradictions: "职业是工程师" vs "职业是医生".
        """
        # Simple contradiction detection via opposing terms
        contradiction_pairs = [
            ("是", "不是"),
            ("有", "没有"),
            ("需要", "不需要"),
            ("支持", "不支持"),
            ("喜欢", "不喜欢"),
            ("is", "is not"),
            ("has", "does not have"),
            ("can", "cannot"),
        ]

        for pos, neg in contradiction_pairs:
            if (pos in existing and neg in new) or (neg in existing and pos in new):
                # Check if they refer to the same subject
                existing_topic = self._extract_topic(existing)
                new_topic = self._extract_topic(new)
                if existing_topic and new_topic and existing_topic == new_topic:
                    return True

        return False

    # ------------------------------------------------------------------
    # Resolution strategies
    # ------------------------------------------------------------------

    def _resolve_duplicate(
        self,
        user_id: str,
        existing_key: str,
        existing_content: str,
        existing_confidence: float,
        new_content: str,
        new_confidence: float,
    ) -> ConflictDetectionResult:
        """Resolve duplicate: dedup + update access count.

        Per spec: "去重合并，更新访问频次"
        """
        # Update access count on existing memory
        self._update_access_count(user_id, existing_key)

        # If new has higher confidence, upgrade existing
        should_upgrade = new_confidence > existing_confidence + 0.1

        reason = "重复信息，已去重合并"
        if should_upgrade:
            reason += f"，新置信度({new_confidence:.2f})更高，升级现有记忆"

        self._log_conflict(ConflictRecord(
            user_id=user_id,
            existing_memory_id=existing_key,
            new_content=new_content,
            existing_content=existing_content,
            conflict_type=ConflictType.DUPLICATE,
            resolution=ConflictResolution.MERGE if not should_upgrade else ConflictResolution.OVERWRITE,
            resolution_reason=reason,
            existing_confidence=existing_confidence,
            new_confidence=new_confidence,
        ))

        return ConflictDetectionResult(
            has_conflict=True,
            conflict_type=ConflictType.DUPLICATE,
            existing_memory_id=existing_key,
            existing_content=existing_content,
            existing_confidence=existing_confidence,
            resolution=ConflictResolution.OVERWRITE if should_upgrade else ConflictResolution.MERGE,
            resolution_reason=reason,
            should_write=should_upgrade,  # Only write if upgrading confidence
        )

    def _resolve_value_update(
        self,
        user_id: str,
        existing_key: str,
        existing_content: str,
        existing_confidence: float,
        existing_source: str,
        new_content: str,
        new_confidence: float,
        new_source: str,
        category: str,
    ) -> ConflictDetectionResult:
        """Resolve value update / preference change.

        Per spec:
        - Value update: Timestamp overwrite + preserve history
        - Preference change: Timestamp overwrite + log change

        Resolution priority:
        1. Explicit confirmation takes precedence
        2. High confidence overwrites low confidence (diff > 0.2)
        3. Same confidence: newer wins
        """
        # Rule 1: Explicit confirmation takes precedence
        new_is_explicit = new_source == "explicit_confirmation"
        existing_is_explicit = existing_source == "explicit_confirmation"

        if new_is_explicit and not existing_is_explicit:
            resolution = ConflictResolution.OVERWRITE
            reason = "新信息来自显式确认，优先级最高"
        elif existing_is_explicit and not new_is_explicit:
            resolution = ConflictResolution.DISCARD_NEW
            reason = "现有信息来自显式确认，保留现有"
        # Rule 2: High confidence overwrites low confidence (diff > 0.2)
        elif new_confidence - existing_confidence > self.CONFIDENCE_OVERWRITE_THRESHOLD:
            resolution = ConflictResolution.OVERWRITE
            reason = f"新置信度({new_confidence:.2f})显著高于现有({existing_confidence:.2f})"
        elif existing_confidence - new_confidence > self.CONFIDENCE_OVERWRITE_THRESHOLD:
            resolution = ConflictResolution.DISCARD_NEW
            reason = f"现有置信度({existing_confidence:.2f})显著高于新({new_confidence:.2f})"
        # Rule 3: Same confidence, newer wins
        elif new_confidence >= existing_confidence:
            resolution = ConflictResolution.OVERWRITE
            reason = "置信度相近，时间戳新者优先"
        else:
            resolution = ConflictResolution.PRESERVE
            reason = "无法确定优先级，保留现有并标记冲突"

        conflict_type = (
            ConflictType.PREFERENCE_CHANGE if category == "preference"
            else ConflictType.VALUE_UPDATE
        )

        self._log_conflict(ConflictRecord(
            user_id=user_id,
            existing_memory_id=existing_key,
            new_content=new_content,
            existing_content=existing_content,
            conflict_type=conflict_type,
            resolution=resolution,
            resolution_reason=reason,
            existing_confidence=existing_confidence,
            new_confidence=new_confidence,
        ))

        should_write = resolution in (ConflictResolution.OVERWRITE, ConflictResolution.MERGE)

        return ConflictDetectionResult(
            has_conflict=True,
            conflict_type=conflict_type,
            existing_memory_id=existing_key,
            existing_content=existing_content,
            existing_confidence=existing_confidence,
            resolution=resolution,
            resolution_reason=reason,
            should_write=should_write,
        )

    def _resolve_contradiction(
        self,
        user_id: str,
        existing_key: str,
        existing_content: str,
        existing_confidence: float,
        existing_source: str,
        new_content: str,
        new_confidence: float,
        new_source: str,
    ) -> ConflictDetectionResult:
        """Resolve contradictory information.

        Per spec: "置信度仲裁 + 人工确认"

        Resolution priority:
        1. Explicit confirmation takes precedence
        2. High confidence overwrites low confidence (diff > 0.2)
        3. Same confidence: preserve existing + mark conflict (escalate)
        """
        # Rule 1: Explicit confirmation
        new_is_explicit = new_source == "explicit_confirmation"
        existing_is_explicit = existing_source == "explicit_confirmation"

        if new_is_explicit and not existing_is_explicit:
            resolution = ConflictResolution.OVERWRITE
            reason = "矛盾信息：新信息来自显式确认，覆盖现有"
        elif existing_is_explicit and not new_is_explicit:
            resolution = ConflictResolution.DISCARD_NEW
            reason = "矛盾信息：现有信息来自显式确认，保留现有"
        # Rule 2: Confidence arbitration
        elif new_confidence - existing_confidence > self.CONFIDENCE_OVERWRITE_THRESHOLD:
            resolution = ConflictResolution.OVERWRITE
            reason = f"矛盾信息：新置信度({new_confidence:.2f})显著高于现有({existing_confidence:.2f})"
        elif existing_confidence - new_confidence > self.CONFIDENCE_OVERWRITE_THRESHOLD:
            resolution = ConflictResolution.DISCARD_NEW
            reason = f"矛盾信息：现有置信度({existing_confidence:.2f})显著高于新({new_confidence:.2f})"
        # Rule 4: Unresolvable — preserve + mark conflict
        else:
            resolution = ConflictResolution.ESCALATE
            reason = "矛盾信息无法仲裁，标记冲突待人工确认"

        self._log_conflict(ConflictRecord(
            user_id=user_id,
            existing_memory_id=existing_key,
            new_content=new_content,
            existing_content=existing_content,
            conflict_type=ConflictType.CONTRADICTION,
            resolution=resolution,
            resolution_reason=reason,
            existing_confidence=existing_confidence,
            new_confidence=new_confidence,
        ))

        should_write = resolution in (ConflictResolution.OVERWRITE, ConflictResolution.MERGE)

        return ConflictDetectionResult(
            has_conflict=True,
            conflict_type=ConflictType.CONTRADICTION,
            existing_memory_id=existing_key,
            existing_content=existing_content,
            existing_confidence=existing_confidence,
            resolution=resolution,
            resolution_reason=reason,
            should_write=should_write,
        )

    # ------------------------------------------------------------------
    # Memory search helpers
    # ------------------------------------------------------------------

    async def _find_related_memories(
        self,
        user_id: str,
        memory_type: MemoryType,
        category: str,
    ) -> list[dict[str, Any]]:
        """Find existing memories that might conflict with a new write."""
        from app.models.memory import MemoryQuery

        mq = MemoryQuery(
            memory_type=memory_type,
            tags=[category] if category else [],
            limit=20,
        )

        records = await memory_orchestrator.search(user_id, memory_type, mq)

        results: list[dict[str, Any]] = []
        for record in records:
            data = record.data
            data["_key"] = record.key
            results.append(data)

        return results

    # ------------------------------------------------------------------
    # Utility helpers
    # ------------------------------------------------------------------

    def _normalize_text(self, text: str) -> str:
        """Normalize text for comparison."""
        # Lowercase, strip whitespace, remove punctuation
        import re
        text = text.lower().strip()
        text = re.sub(r'[^\w\s]', '', text)
        text = re.sub(r'\s+', ' ', text)
        return text

    def _extract_topic(self, text: str) -> str:
        """Extract the topic/subject from a memory text.

        Simple heuristic: extract the part before the value assignment.
        E.g., "用户偏好使用Python" → "用户偏好使用"
        """
        import re

        # Try to find topic-value patterns
        patterns = [
            r'(.+?)(?:是|为|用|使用|偏好|喜欢|习惯)\s*(.+)',
            r'(.+?)(?:is|are|prefer|like|use)\s+(.+)',
        ]

        for pattern in patterns:
            match = re.match(pattern, text.strip())
            if match:
                return match.group(1).strip()

        # Fallback: first N characters
        return text[:min(20, len(text))].strip()

    async def _update_access_count(self, user_id: str, key: str) -> None:
        """Update access count for an existing memory."""
        try:
            record = await memory_orchestrator.read_semantic(user_id, key)
            if record and record.data:
                data = record.data
                data["access_count"] = data.get("access_count", 0) + 1
                data["last_accessed_at"] = datetime.now(timezone.utc).isoformat()
                await memory_orchestrator.write_semantic(user_id, key, data)
        except Exception as e:
            logger.warning("Failed to update access count for %s: %s", key, e)

    def _log_conflict(self, record: ConflictRecord) -> None:
        """Log a conflict record.

        S5.7: Also emits audit event for conflict resolution.
        """
        self._conflict_log.append(record)
        if len(self._conflict_log) > self._max_log_size:
            self._conflict_log = self._conflict_log[-self._max_log_size:]

        logger.info(
            "Conflict resolved: user=%s, type=%s, resolution=%s, reason=%s",
            record.user_id, record.conflict_type, record.resolution,
            record.resolution_reason,
        )

        # S5.7: Audit conflict resolution (non-blocking)
        try:
            import asyncio
            from app.layers.security.audit_logger import audit_logger
            loop = asyncio.get_event_loop()
            if loop.is_running():
                loop.create_task(audit_logger.log(
                    event_type="memory_conflict_resolve",
                    user_id=record.user_id,
                    session_id="",
                    task_id="",
                    details={
                        "conflict_id": record.conflict_id,
                        "existing_memory_id": record.existing_memory_id,
                        "conflict_type": record.conflict_type,
                        "resolution": record.resolution,
                        "resolution_reason": record.resolution_reason,
                        "existing_confidence": record.existing_confidence,
                        "new_confidence": record.new_confidence,
                    },
                    severity="INFO",
                ))
        except Exception as e:
            logger.debug("Audit conflict resolve failed (non-blocking): %s", e)

    # ------------------------------------------------------------------
    # Query conflict history
    # ------------------------------------------------------------------

    def get_conflict_history(
        self,
        user_id: str = "",
        conflict_type: str = "",
        limit: int = 20,
    ) -> list[ConflictRecord]:
        """Get conflict resolution history, optionally filtered."""
        records = self._conflict_log

        if user_id:
            records = [r for r in records if r.user_id == user_id]
        if conflict_type:
            records = [r for r in records if r.conflict_type == conflict_type]

        return records[-limit:]

    async def mark_conflict_resolved(
        self,
        user_id: str,
        memory_id: str,
        resolution: str,
    ) -> bool:
        """Mark a conflicting memory as resolved.

        Updates the conflict_info on the memory chunk.
        """
        try:
            record = await memory_orchestrator.read_semantic(user_id, memory_id)
            if record and record.data:
                data = record.data
                data["conflict_info"] = {
                    "has_conflict": False,
                    "resolution_status": resolution,
                }
                await memory_orchestrator.write_semantic(user_id, memory_id, data)
                logger.info("Marked conflict resolved for memory %s", memory_id)
                return True
        except Exception as e:
            logger.warning("Failed to mark conflict resolved for %s: %s", memory_id, e)

        return False


# Global singleton
memory_conflict_resolver = MemoryConflictResolver()
