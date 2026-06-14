from collections import OrderedDict
from threading import RLock
from typing import Any


class L0Cache:
    """Thread-safe LRU cache for local shard storage."""

    def __init__(self, max_size: int = 256) -> None:
        self._cache: OrderedDict[str, Any] = OrderedDict()
        self._lock = RLock()
        self._max_size = max_size
        self._hit_count: int = 0
        self._miss_count: int = 0

    def get(self, key: str) -> Any | None:
        with self._lock:
            if key in self._cache:
                self._cache.move_to_end(key)
                self._hit_count += 1
                return self._cache[key]
            self._miss_count += 1
        return None

    def set(self, key: str, value: Any) -> None:
        with self._lock:
            if len(self._cache) >= self._max_size:
                self._cache.popitem(last=False)
            self._cache[key] = value
            self._cache.move_to_end(key)

    def invalidate(self, key: str) -> None:
        with self._lock:
            self._cache.pop(key, None)

    def resize(self, max_size: int) -> None:
        """Dynamically adjust max_size, evicting LRU entries if shrinking."""
        with self._lock:
            self._max_size = max_size
            while len(self._cache) > self._max_size:
                self._cache.popitem(last=False)

    def stats(self) -> dict[str, int | float]:
        """Return cache statistics: size, max_size, hit_count, miss_count, hit_rate."""
        total = self._hit_count + self._miss_count
        return {
            "size": len(self._cache),
            "max_size": self._max_size,
            "hit_count": self._hit_count,
            "miss_count": self._miss_count,
            "hit_rate": self._hit_count / total if total > 0 else 0.0,
        }

    def clear(self) -> None:
        """Clear all entries and reset counters."""
        with self._lock:
            self._cache.clear()
            self._hit_count = 0
            self._miss_count = 0

    def keys(self) -> list[str]:
        """Return a list of all cache keys (snapshot, thread-safe)."""
        with self._lock:
            return list(self._cache.keys())

    def items(self) -> list[tuple[str, Any]]:
        """Return a list of all (key, value) pairs (snapshot, thread-safe)."""
        with self._lock:
            return list(self._cache.items())

    def __len__(self) -> int:
        return len(self._cache)
