import pytest
import fakeredis

from app.config import Settings


@pytest.fixture
def test_settings() -> Settings:
    return Settings(
        app_env="test",
        redis_url="redis://localhost:6379/1",
        java_base_url="http://test-java:8080",
        llm_api_key="test-key",
        llm_base_url="http://test-llm:8080",
    )


@pytest.fixture(autouse=True)
def _patch_redis(monkeypatch):
    """Auto-use fixture: patch redis_client to use FakeAsyncRedis for all tests."""
    fake_redis = fakeredis.FakeAsyncRedis()

    async def _get_fake_redis():
        return fake_redis

    from app.infrastructure.redis_client import redis_client
    monkeypatch.setattr(redis_client, "get_redis", _get_fake_redis)
    monkeypatch.setattr(redis_client, "_redis", fake_redis)
