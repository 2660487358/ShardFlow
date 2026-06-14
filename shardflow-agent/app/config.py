from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    model_config = {
        "env_prefix": "SF_AGENT_",
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "extra": "allow",
    }

    # ── 基础配置 ──
    app_env: str = "dev"
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    redis_url: str = "redis://localhost:6379/0"
    java_base_url: str = "http://java-service:8200"
    llm_api_key: str = ""
    llm_base_url: str = ""
    log_level: str = "INFO"

    # ── 服务间认证 ──
    java_api_key: str = ""

    # ── 模型加密主密钥 ──
    model_key_master: str = ""

    # ── 厂商 API Keys ──
    openai_api_key: str = ""
    deepseek_api_key: str = ""
    anthropic_api_key: str = ""
    azure_openai_api_key: str = ""

    # ── 外部检索源 ──
    stackexchange_api_key: str = ""
    github_token: str = ""

    # ── 检索行为配置 ──
    retrieval_sources_enabled: str = "official_doc,stackoverflow,github"
    retrieval_timeout: float = 10.0
    retrieval_fallback_to_mock: bool = False

    # ── 首字延迟优化开关 ──
    # 答案流式模式: realtime=实时转发, buffer=二次缓冲回放(旧行为,仅回滚用)
    answer_streaming_mode: str = "realtime"
    # 是否跳过图中重复的意图识别 LLM 调用(API 层已识别)
    skip_duplicate_intent: bool = True
    # 是否启用 HTTP/2 多路复用(需 pip install httpx[http2])
    llm_http2: bool = False

    # ── 知识库（Milvus + Embedding）──
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
    grpc_port: int = 50051

    # ── MinIO ──
    minio_endpoint: str = "localhost:9000"
    minio_access_key: str = "minioadmin"
    minio_secret_key: str = "minioadmin"
    minio_bucket: str = "shardflow-kb"

    # ── RabbitMQ ──
    rabbitmq_host: str = "localhost"
    rabbitmq_port: int = 5672
    rabbitmq_user: str = "guest"
    rabbitmq_password: str = "guest"
    rabbitmq_vhost: str = "/"

    # ── 输出行为规范配置（企业级Agent模型输出行为规范）──
    # 思考过程展示模式: hidden=完全隐藏 | summary=一句话摘要 | detailed=折叠面板
    thinking_visibility: str = "hidden"
    # 后处理流水线开关
    post_processing_tag_parsing: bool = True
    post_processing_isolation_validation: bool = True
    post_processing_meta_comment_filter: bool = True
    post_processing_format_normalization: bool = True
    post_processing_safety_scan: bool = True
    # 元评论过滤强度: strict=严格 | moderate=中等 | lenient=宽松
    meta_comment_filter_level: str = "strict"
    # 降级策略
    degradation_p0_fatal: str = "block_with_fallback"
    degradation_p1_severe: str = "regenerate_from_thinking"
    degradation_p2_general: str = "auto_clean_with_log"
    degradation_p3_minor: str = "auto_fix_with_suggestion"
    # 工具调用信息展示
    tool_call_show_tool_name: bool = False
    tool_call_show_call_params: bool = False
    tool_call_show_call_count: bool = False
    tool_call_show_execution_time: bool = False
    tool_call_show_data_source: bool = True
    tool_call_show_result_summary: bool = True


settings = Settings()
