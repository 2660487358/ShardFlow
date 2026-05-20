from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}

    app_env: str = "dev"
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    redis_url: str = "redis://localhost:6379/0"
    java_base_url: str = "http://java-service:8080"
    llm_api_key: str = ""
    llm_base_url: str = ""
    log_level: str = "INFO"
    shard_cache_ttl: int = 1800


settings = Settings()
