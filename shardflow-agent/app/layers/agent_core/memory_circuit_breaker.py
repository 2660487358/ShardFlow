"""MemoryCircuitBreaker — 记忆操作统一熔断降级器。

实现滑动窗口失败计数、半开状态探测、自动恢复机制。
当记忆操作连续失败达到阈值时，熔断器打开，跳过记忆操作；
半开状态下允许有限探测请求，探测成功则自动恢复。

状态机:
  CLOSED → (连续失败 >= threshold) → OPEN
  OPEN → (超时后) → HALF_OPEN
  HALF_OPEN → (探测成功) → CLOSED
  HALF_OPEN → (探测失败) → OPEN
"""
import asyncio
import logging
import time
from collections import deque
from enum import Enum
from typing import Any, Callable, Coroutine, TypeVar

logger = logging.getLogger(__name__)

T = TypeVar("T")


class CircuitState(str, Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class MemoryCircuitBreaker:
    """Unified circuit breaker for all memory operations.

    Config (from settings, with defaults):
    - MEMORY_CB_FAILURE_THRESHOLD: consecutive failures to open (default 5)
    - MEMORY_CB_TIMEOUT_SECONDS: seconds before half-open (default 60)
    - MEMORY_CB_HALF_OPEN_LIMIT: max probes in half-open state (default 3)
    """

    def __init__(
        self,
        failure_threshold: int = 5,
        timeout_seconds: int = 60,
        half_open_limit: int = 3,
    ) -> None:
        self._failure_threshold = failure_threshold
        self._timeout_seconds = timeout_seconds
        self._half_open_limit = half_open_limit

        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._last_failure_time: float = 0.0
        self._half_open_successes = 0
        self._half_open_failures = 0

        # Sliding window for metrics
        self._recent_calls: deque[dict[str, Any]] = deque(maxlen=100)

    # ------------------------------------------------------------------
    # Configuration from settings
    # ------------------------------------------------------------------

    @classmethod
    def from_settings(cls) -> "MemoryCircuitBreaker":
        """Create a MemoryCircuitBreaker with values from app settings."""
        try:
            from app.config import settings
            return cls(
                failure_threshold=getattr(settings, "memory_cb_failure_threshold", 5),
                timeout_seconds=getattr(settings, "memory_cb_timeout_seconds", 60),
                half_open_limit=getattr(settings, "memory_cb_half_open_limit", 3),
            )
        except Exception:
            return cls()

    # ------------------------------------------------------------------
    # State machine
    # ------------------------------------------------------------------

    @property
    def state(self) -> CircuitState:
        """Current circuit state, with automatic transition from OPEN to HALF_OPEN."""
        if self._state == CircuitState.OPEN:
            if time.monotonic() - self._last_failure_time >= self._timeout_seconds:
                self._state = CircuitState.HALF_OPEN
                self._half_open_successes = 0
                self._half_open_failures = 0
                logger.info("MemoryCircuitBreaker: OPEN → HALF_OPEN (timeout elapsed)")
        return self._state

    @property
    def is_open(self) -> bool:
        """Whether the circuit is open (operations should be skipped)."""
        current = self.state
        if current == CircuitState.OPEN:
            return True
        if current == CircuitState.HALF_OPEN:
            # In half-open, allow limited probes
            return self._half_open_failures >= self._half_open_limit
        return False

    def record_success(self) -> None:
        """Record a successful operation."""
        self._recent_calls.append({"time": time.monotonic(), "success": True})

        if self._state == CircuitState.HALF_OPEN:
            self._half_open_successes += 1
            if self._half_open_successes >= self._half_open_limit:
                self._state = CircuitState.CLOSED
                self._failure_count = 0
                logger.info("MemoryCircuitBreaker: HALF_OPEN → CLOSED (probes succeeded)")
        elif self._state == CircuitState.CLOSED:
            self._failure_count = 0

    def record_failure(self) -> None:
        """Record a failed operation."""
        self._recent_calls.append({"time": time.monotonic(), "success": False})
        self._failure_count += 1
        self._last_failure_time = time.monotonic()

        if self._state == CircuitState.HALF_OPEN:
            self._half_open_failures += 1
            if self._half_open_failures >= self._half_open_limit:
                self._state = CircuitState.OPEN
                logger.warning(
                    "MemoryCircuitBreaker: HALF_OPEN → OPEN (probes failed, %d/%d)",
                    self._half_open_failures, self._half_open_limit,
                )
        elif self._state == CircuitState.CLOSED:
            if self._failure_count >= self._failure_threshold:
                self._state = CircuitState.OPEN
                logger.warning(
                    "MemoryCircuitBreaker: CLOSED → OPEN (consecutive failures: %d)",
                    self._failure_count,
                )

    def reset(self) -> None:
        """Manually reset the circuit breaker to CLOSED state."""
        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._half_open_successes = 0
        self._half_open_failures = 0
        logger.info("MemoryCircuitBreaker: manually reset to CLOSED")

    # ------------------------------------------------------------------
    # Protected execution
    # ------------------------------------------------------------------

    async def call(
        self,
        fn: Callable[..., Coroutine[Any, Any, T]],
        *args: Any,
        fallback: T | None = None,
        **kwargs: Any,
    ) -> T | None:
        """Execute an async function with circuit breaker protection.

        If the circuit is open, returns fallback immediately.
        On success, records success; on failure, records failure and returns fallback.
        """
        if self.is_open:
            logger.debug("MemoryCircuitBreaker: circuit open, skipping operation")
            return fallback

        try:
            result = await fn(*args, **kwargs)
            self.record_success()
            return result
        except Exception as e:
            self.record_failure()
            logger.warning("MemoryCircuitBreaker: operation failed: %s", e)
            return fallback

    # ------------------------------------------------------------------
    # Metrics
    # ------------------------------------------------------------------

    def get_stats(self) -> dict[str, Any]:
        """Get circuit breaker statistics."""
        now = time.monotonic()
        recent_successes = sum(
            1 for c in self._recent_calls
            if c["success"] and now - c["time"] < 300  # last 5 minutes
        )
        recent_failures = sum(
            1 for c in self._recent_calls
            if not c["success"] and now - c["time"] < 300
        )

        return {
            "state": self.state.value,
            "failure_count": self._failure_count,
            "failure_threshold": self._failure_threshold,
            "last_failure_time": self._last_failure_time,
            "recent_successes_5m": recent_successes,
            "recent_failures_5m": recent_failures,
        }


# Global singleton — lazy initialization from settings
_memory_circuit_breaker: MemoryCircuitBreaker | None = None


def get_memory_circuit_breaker() -> MemoryCircuitBreaker:
    """Get the global MemoryCircuitBreaker singleton."""
    global _memory_circuit_breaker
    if _memory_circuit_breaker is None:
        _memory_circuit_breaker = MemoryCircuitBreaker.from_settings()
    return _memory_circuit_breaker
