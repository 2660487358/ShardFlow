from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    model_config = {"env_file": ".env", "env_file_encoding": "utf-8", "extra": "allow"}

    app_env: str = "dev"
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    redis_url: str = "redis://localhost:6379/0"
    java_base_url: str = "http://java-service:8080"  # env: SHARDFLOW_JAVA_BASE_URL
    llm_api_key: str = ""
    llm_base_url: str = ""
    log_level: str = "INFO"
    shard_cache_ttl: int = 1800

    # Java 外围服务独立 API Key（不复用 llm_api_key）
    java_api_key: str = ""

    # 检索源 API 认证
    stackexchange_api_key: str = ""
    github_token: str = ""

    # 检索源开关：支持按源启用/禁用
    retrieval_sources_enabled: str = "official_doc,stackoverflow,github"

    # 检索源超时（秒）
    retrieval_timeout: float = 10.0

    # 检索源降级：true 时 API 失败自动降级到 Mock 源
    retrieval_fallback_to_mock: bool = True


settings = Settings()
