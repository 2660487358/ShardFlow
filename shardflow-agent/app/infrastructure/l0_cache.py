from collections import OrderedDict
from threading import RLock
from typing import Any


class L0Cache:
    """Thread-safe LRU cache for local shard storage."""

    def __init__(self, max_size: int = 256) -> None:
        self._cache: OrderedDict[str, Any] = OrderedDict()
        self._lock = RLock()
        self._max_size = max_size

    def get(self, key: str) -> Any | None:
        with self._lock:
            if key in self._cache:
                self._cache.move_to_end(key)
                return self._cache[key]
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
