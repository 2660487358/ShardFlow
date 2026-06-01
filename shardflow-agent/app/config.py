from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    model_config = {
        "env_prefix": "SF_AGENT_",
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "extra": "allow",
    }

    app_env: str = "dev"
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    redis_url: str = "redis://localhost:6379/0"
    java_base_url: str = "http://java-service:8200"
    llm_api_key: str = ""
    llm_base_url: str = ""
    log_level: str = "INFO"
    shard_cache_ttl: int = 1800

    java_api_key: str = ""

    stackexchange_api_key: str = ""
    github_token: str = ""

    retrieval_sources_enabled: str = "official_doc,stackoverflow,github"
    retrieval_timeout: float = 10.0
    retrieval_fallback_to_mock: bool = True

    milvus_host: str = "localhost"
    milvus_port: int = 19530
    milvus_db_name: str = "shardflow_kb"
    kb_embedding_model: str = "text-embedding-3-small"
    kb_embedding_dim: int = 768
    kb_chunk_size: int = 512
    kb_chunk_overlap: int = 64
    kb_embedding_batch_size: int = 20
    kb_retrieval_top_k: int = 10
    kb_retrieval_similarity_threshold: float = 0.65
    kb_upload_dir: str = "./uploads/kb"
    kb_supported_extensions: str = ".pdf,.docx,.md,.txt,.py,.java,.ts,.tsx,.js,.go,.rs,.yaml,.yml,.json,.xml"
    kb_max_file_size_mb: int = 20
    kb_enabled: bool = True


settings = Settings()
