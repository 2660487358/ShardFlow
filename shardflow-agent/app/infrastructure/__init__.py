"""Infrastructure — Cross-cutting technical components."""

from app.infrastructure.redis_client import redis_client
from app.infrastructure.callback_client import callback_client
from app.infrastructure.optimistic_lock import optimistic_lock, OptimisticLock

__all__ = [
    "redis_client",
    "callback_client",
    "optimistic_lock", "OptimisticLock",
]
