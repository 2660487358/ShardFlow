"""MemoryMetrics — 记忆架构监控指标收集器 (P7.3 + 4B).

Implements P7.3 monitoring metrics:
- P7.3.1: 记忆命中率监控 — L0/L1/L2 命中率
- P7.3.2: 记忆新鲜度监控 — 最近访问时间分布
- P7.3.3: 记忆压缩率监控 — 压缩前后 token 比率
- P7.3.4: 用户画像完整度监控 — 画像字段覆盖率

Phase 4B metrics:
- 4B-01: injection_token_ratio — 注入 Token 占比
- 4B-01: memory_hit — 是否有匹配记忆
- 4B-01: llm_reference_rate — LLM 是否引用记忆
- 4B-02: assembly metrics — 装配耗时、各 section Token 数、总 Token 数、是否溢出
"""
import threading
from collections import OrderedDict
from datetime import datetime, timezone
from typing import Any


class MemoryMetrics:
    """记忆架构监控指标收集器。

    收集和报告记忆架构的关键性能指标：
    - 命中率：L0/L1/L2 各级缓存的命中/未命中统计
    - 新鲜度：记忆最近访问时间的分布统计
    - 压缩率：LLM 压缩前后 token 数比率
    - 画像完整度：用户画像字段覆盖率
    """

    VALID_TIERS = ("L0", "L1", "L2")
    MAX_ACCESS_RECORDS = 10000
    MAX_COMPRESSION_RECORDS = 1000
    MAX_ASSEMBLY_RECORDS = 1000
    MAX_REFERENCE_RECORDS = 1000

    # Freshness distribution buckets
    FRESHNESS_BUCKETS = ["<1h", "1h-6h", "6h-24h", "1d-7d", ">7d"]

    def __init__(self) -> None:
        self._lock = threading.Lock()

        # P7.3.1: Hit rate counters per tier
        self._hits: dict[str, int] = {tier: 0 for tier in self.VALID_TIERS}
        self._misses: dict[str, int] = {tier: 0 for tier in self.VALID_TIERS}

        # P7.3.2: Freshness tracking — memory_id -> (memory_type, last_access_time)
        self._access_times: OrderedDict[str, tuple[str, datetime]] = OrderedDict()

        # P7.3.3: Compression records — list of (original, compressed)
        self._compression_records: list[tuple[int, int]] = []

        # P7.3.4: Profile completeness — user_id -> (total_fields, filled_fields)
        self._profile_completeness: dict[str, tuple[int, int]] = {}

        # 4B-01: Memory hit tracking — total rounds with/without memory match
        self._memory_hit_count: int = 0
        self._memory_miss_count: int = 0

        # 4B-01: Injection token ratio records — list of (injected_tokens, total_context_tokens)
        self._injection_ratio_records: list[tuple[int, int]] = []

        # 4B-01: LLM reference rate tracking — total responses / referenced count
        self._llm_response_count: int = 0
        self._llm_referenced_count: int = 0

        # 4B-02: Assembly metrics — list of assembly records
        self._assembly_records: list[dict[str, Any]] = []

    # ------------------------------------------------------------------
    # P7.3.1: Hit rate monitoring
    # ------------------------------------------------------------------

    def record_hit(self, tier: str) -> None:
        """Record a cache hit for the given tier.

        Args:
            tier: One of "L0", "L1", "L2".
        """
        if tier not in self.VALID_TIERS:
            return
        with self._lock:
            self._hits[tier] += 1

    def record_miss(self, tier: str) -> None:
        """Record a cache miss for the given tier.

        Args:
            tier: One of "L0", "L1", "L2".
        """
        if tier not in self.VALID_TIERS:
            return
        with self._lock:
            self._misses[tier] += 1

    def get_hit_rates(self) -> dict[str, float]:
        """Get hit rate for each tier (0.0-1.0).

        Returns:
            Dict mapping tier name to hit rate. Returns 0.0 if no
            hits or misses recorded for a tier.
        """
        with self._lock:
            rates: dict[str, float] = {}
            for tier in self.VALID_TIERS:
                total = self._hits[tier] + self._misses[tier]
                rates[tier] = self._hits[tier] / total if total > 0 else 0.0
            return rates

    def get_hit_stats(self) -> dict[str, dict[str, Any]]:
        """Get detailed hit/miss stats per tier.

        Returns:
            Dict mapping tier name to {"hits": int, "misses": int, "hit_rate": float}.
        """
        with self._lock:
            stats: dict[str, dict[str, Any]] = {}
            for tier in self.VALID_TIERS:
                hits = self._hits[tier]
                misses = self._misses[tier]
                total = hits + misses
                stats[tier] = {
                    "hits": hits,
                    "misses": misses,
                    "hit_rate": hits / total if total > 0 else 0.0,
                }
            return stats

    # ------------------------------------------------------------------
    # P7.3.2: Freshness monitoring
    # ------------------------------------------------------------------

    def record_access(self, memory_id: str, memory_type: str) -> None:
        """Record a memory access for freshness tracking.

        Args:
            memory_id: Unique identifier of the memory entry.
            memory_type: Type of memory (e.g. "semantic", "episodic").
        """
        with self._lock:
            # LRU eviction if at capacity
            if len(self._access_times) >= self.MAX_ACCESS_RECORDS and memory_id not in self._access_times:
                self._access_times.popitem(last=False)

            self._access_times[memory_id] = (memory_type, datetime.now(timezone.utc))

    def get_freshness_distribution(self) -> dict[str, int]:
        """Get distribution of memory ages across time buckets.

        Buckets: <1h, 1h-6h, 6h-24h, 1d-7d, >7d

        Returns:
            Dict mapping bucket name to count of memories in that bucket.
        """
        now = datetime.now(timezone.utc)
        distribution: dict[str, int] = {bucket: 0 for bucket in self.FRESHNESS_BUCKETS}

        with self._lock:
            access_snapshot = list(self._access_times.values())

        for _memory_type, access_time in access_snapshot:
            age = now - access_time
            age_seconds = age.total_seconds()

            if age_seconds < 3600:
                distribution["<1h"] += 1
            elif age_seconds < 21600:  # 6 hours
                distribution["1h-6h"] += 1
            elif age_seconds < 86400:  # 24 hours
                distribution["6h-24h"] += 1
            elif age_seconds < 604800:  # 7 days
                distribution["1d-7d"] += 1
            else:
                distribution[">7d"] += 1

        return distribution

    # ------------------------------------------------------------------
    # P7.3.3: Compression ratio monitoring
    # ------------------------------------------------------------------

    def record_compression(self, original_tokens: int, compressed_tokens: int) -> None:
        """Record a compression event.

        Args:
            original_tokens: Token count before compression.
            compressed_tokens: Token count after compression.
        """
        if original_tokens <= 0 or compressed_tokens < 0:
            return
        with self._lock:
            if len(self._compression_records) >= self.MAX_COMPRESSION_RECORDS:
                self._compression_records.pop(0)
            self._compression_records.append((original_tokens, compressed_tokens))

    def get_compression_stats(self) -> dict[str, Any]:
        """Get compression statistics.

        Returns:
            Dict with keys: total_compressions, avg_ratio, min_ratio, max_ratio.
            Returns zeroed stats if no compression records exist.
        """
        with self._lock:
            records = list(self._compression_records)

        if not records:
            return {
                "total_compressions": 0,
                "avg_ratio": 0.0,
                "min_ratio": 0.0,
                "max_ratio": 0.0,
            }

        ratios = [c / o for o, c in records if o > 0]
        if not ratios:
            return {
                "total_compressions": len(records),
                "avg_ratio": 0.0,
                "min_ratio": 0.0,
                "max_ratio": 0.0,
            }

        return {
            "total_compressions": len(records),
            "avg_ratio": sum(ratios) / len(ratios),
            "min_ratio": min(ratios),
            "max_ratio": max(ratios),
        }

    # ------------------------------------------------------------------
    # P7.3.4: Profile completeness monitoring
    # ------------------------------------------------------------------

    def record_profile_completeness(
        self, user_id: str, total_fields: int, filled_fields: int,
    ) -> None:
        """Record profile completeness for a user.

        Args:
            user_id: User identifier.
            total_fields: Total number of profile fields.
            filled_fields: Number of fields with actual values.
        """
        if total_fields <= 0:
            return
        with self._lock:
            self._profile_completeness[user_id] = (total_fields, min(filled_fields, total_fields))

    def get_profile_completeness(self, user_id: str) -> float:
        """Get completeness ratio for a specific user (0.0-1.0).

        Args:
            user_id: User identifier.

        Returns:
            Completeness ratio, or 0.0 if user not tracked.
        """
        with self._lock:
            entry = self._profile_completeness.get(user_id)
        if entry is None:
            return 0.0
        total, filled = entry
        return filled / total if total > 0 else 0.0

    def get_average_profile_completeness(self) -> float:
        """Get average completeness across all tracked users.

        Returns:
            Average completeness ratio (0.0-1.0), or 0.0 if no users tracked.
        """
        with self._lock:
            entries = list(self._profile_completeness.values())
        if not entries:
            return 0.0
        ratios = [filled / total for total, filled in entries if total > 0]
        return sum(ratios) / len(ratios) if ratios else 0.0

    # ------------------------------------------------------------------
    # 4B-01: Memory hit tracking
    # ------------------------------------------------------------------

    def record_memory_hit(self, has_match: bool) -> None:
        """Record whether memory had a matching result for a query.

        Args:
            has_match: True if relevant memory was found and injected.
        """
        with self._lock:
            if has_match:
                self._memory_hit_count += 1
            else:
                self._memory_miss_count += 1

    def get_memory_hit_rate(self) -> float:
        """Get the memory hit rate (0.0-1.0).

        Returns:
            Ratio of rounds where memory was successfully matched.
        """
        with self._lock:
            total = self._memory_hit_count + self._memory_miss_count
            return self._memory_hit_count / total if total > 0 else 0.0

    # ------------------------------------------------------------------
    # 4B-01: Injection token ratio
    # ------------------------------------------------------------------

    def record_injection_token_ratio(
        self, injected_tokens: int, total_context_tokens: int,
    ) -> None:
        """Record the token ratio of memory injection vs total context.

        Args:
            injected_tokens: Number of tokens from memory injection.
            total_context_tokens: Total tokens in the LLM context.
        """
        if total_context_tokens <= 0:
            return
        with self._lock:
            if len(self._injection_ratio_records) >= self.MAX_ASSEMBLY_RECORDS:
                self._injection_ratio_records.pop(0)
            self._injection_ratio_records.append((injected_tokens, total_context_tokens))

    def get_injection_token_ratio_stats(self) -> dict[str, Any]:
        """Get injection token ratio statistics.

        Returns:
            Dict with avg_ratio, min_ratio, max_ratio, sample_count.
        """
        with self._lock:
            records = list(self._injection_ratio_records)

        if not records:
            return {"avg_ratio": 0.0, "min_ratio": 0.0, "max_ratio": 0.0, "sample_count": 0}

        ratios = [injected / total for injected, total in records if total > 0]
        if not ratios:
            return {"avg_ratio": 0.0, "min_ratio": 0.0, "max_ratio": 0.0, "sample_count": len(records)}

        return {
            "avg_ratio": sum(ratios) / len(ratios),
            "min_ratio": min(ratios),
            "max_ratio": max(ratios),
            "sample_count": len(records),
        }

    # ------------------------------------------------------------------
    # 4B-01: LLM reference rate
    # ------------------------------------------------------------------

    def record_llm_reference(self, referenced: bool) -> None:
        """Record whether the LLM response referenced injected memory content.

        Args:
            referenced: True if LLM output contains references to injected memory.
        """
        with self._lock:
            self._llm_response_count += 1
            if referenced:
                self._llm_referenced_count += 1

    def get_llm_reference_rate(self) -> float:
        """Get the LLM reference rate (0.0-1.0).

        Returns:
            Ratio of LLM responses that referenced injected memory content.
        """
        with self._lock:
            total = self._llm_response_count
            return self._llm_referenced_count / total if total > 0 else 0.0

    # ------------------------------------------------------------------
    # 4B-02: Assembly metrics
    # ------------------------------------------------------------------

    def record_assembly(
        self,
        elapsed_ms: float,
        section_tokens: dict[str, int],
        total_tokens: int,
        total_budget: int,
        overflow: bool,
    ) -> None:
        """Record context assembly metrics.

        Args:
            elapsed_ms: Assembly duration in milliseconds.
            section_tokens: Dict mapping section_type -> token count.
            total_tokens: Total assembled tokens.
            total_budget: Token budget for assembly.
            overflow: Whether content exceeded budget.
        """
        with self._lock:
            if len(self._assembly_records) >= self.MAX_ASSEMBLY_RECORDS:
                self._assembly_records.pop(0)
            self._assembly_records.append({
                "elapsed_ms": elapsed_ms,
                "section_tokens": section_tokens,
                "total_tokens": total_tokens,
                "total_budget": total_budget,
                "overflow": overflow,
            })

    def get_assembly_stats(self) -> dict[str, Any]:
        """Get assembly statistics.

        Returns:
            Dict with avg_elapsed_ms, overflow_count, total_assemblies,
            avg_token_usage_ratio.
        """
        with self._lock:
            records = list(self._assembly_records)

        if not records:
            return {
                "avg_elapsed_ms": 0.0,
                "overflow_count": 0,
                "total_assemblies": 0,
                "avg_token_usage_ratio": 0.0,
            }

        elapsed_values = [r["elapsed_ms"] for r in records]
        overflow_count = sum(1 for r in records if r["overflow"])
        usage_ratios = [
            r["total_tokens"] / r["total_budget"]
            for r in records if r["total_budget"] > 0
        ]

        return {
            "avg_elapsed_ms": sum(elapsed_values) / len(elapsed_values),
            "overflow_count": overflow_count,
            "total_assemblies": len(records),
            "avg_token_usage_ratio": sum(usage_ratios) / len(usage_ratios) if usage_ratios else 0.0,
        }

    # ------------------------------------------------------------------
    # Summary & Reset
    # ------------------------------------------------------------------

    def get_summary(self) -> dict[str, Any]:
        """Get a complete summary of all metrics.

        Returns:
            Dict containing hit_stats, freshness_distribution,
            compression_stats, average_profile_completeness,
            tracked_users_count, memory_hit_rate,
            injection_token_ratio_stats, llm_reference_rate,
            assembly_stats.
        """
        return {
            "hit_stats": self.get_hit_stats(),
            "freshness_distribution": self.get_freshness_distribution(),
            "compression_stats": self.get_compression_stats(),
            "average_profile_completeness": self.get_average_profile_completeness(),
            "tracked_users_count": len(self._profile_completeness),
            "memory_hit_rate": self.get_memory_hit_rate(),
            "injection_token_ratio_stats": self.get_injection_token_ratio_stats(),
            "llm_reference_rate": self.get_llm_reference_rate(),
            "assembly_stats": self.get_assembly_stats(),
        }

    def reset(self) -> None:
        """Reset all metrics to initial state."""
        with self._lock:
            self._hits = {tier: 0 for tier in self.VALID_TIERS}
            self._misses = {tier: 0 for tier in self.VALID_TIERS}
            self._access_times.clear()
            self._compression_records.clear()
            self._profile_completeness.clear()
            self._memory_hit_count = 0
            self._memory_miss_count = 0
            self._injection_ratio_records.clear()
            self._llm_response_count = 0
            self._llm_referenced_count = 0
            self._assembly_records.clear()


# Global singleton
memory_metrics = MemoryMetrics()
