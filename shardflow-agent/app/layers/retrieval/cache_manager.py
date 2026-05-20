import hashlib
import json

from app.infrastructure.redis_client import redis_client
from app.models.search_result import SearchResult


class RetrievalCacheManager:
    TTL: int = 300

    def _cache_key(self, tenant_id: str, query: str) -> str:
        qhash = hashlib.sha256(query.encode()).hexdigest()[:16]
        return f"kb:{tenant_id}:search:{qhash}"

    async def get_cache(self, tenant_id: str, query: str) -> list[SearchResult] | None:
        r = await redis_client.get_redis()
        raw = await r.get(self._cache_key(tenant_id, query))
        if raw is None:
            return None
        try:
            data = json.loads(raw)
            return [SearchResult(**item) for item in data]
        except Exception:
            return None

    async def set_cache(self, tenant_id: str, query: str, results: list[SearchResult]) -> None:
        r = await redis_client.get_redis()
        data = [item.model_dump(mode="json") for item in results]
        await r.set(self._cache_key(tenant_id, query), json.dumps(data), ex=self.TTL)

    async def invalidate_cache(self, tenant_id: str, query: str) -> None:
        r = await redis_client.get_redis()
        await r.delete(self._cache_key(tenant_id, query))


retrieval_cache_manager = RetrievalCacheManager()
