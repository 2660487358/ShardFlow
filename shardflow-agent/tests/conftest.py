import pytest

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
