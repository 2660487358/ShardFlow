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

    # ── 记忆架构配置 ──
    # 总开关
    memory_enabled: bool = True

    # 对话窗口（4轮 × 2条/轮 = 8条消息）
    memory_window_size: int = 8
    memory_max_context_tokens: int = 128000

    # 阶段3 P1: L2 概念摘要触发配置
    # 溢出批量压缩阈值：当溢出消息数 >= memory_compress_batch 时触发增量压缩
    memory_compress_batch: int = 4
    # 压缩异步执行开关：True 时 add_message 异步触发压缩，不阻塞首 token
    memory_compress_async: bool = True

    # 压缩与分片阈值
    memory_compress_threshold: float = 0.80
    memory_shard_threshold: float = 0.80
    memory_context_compress_threshold: float = 0.70
    memory_target_compress_ratio: float = 0.25
    memory_corrective_compress_interval: int = 20

    # 上下文压力阈值
    memory_pressure_warning: float = 0.60
    memory_pressure_critical: float = 0.80
    memory_pressure_full: float = 1.00

    # TTL 配置（秒）
    memory_short_term_ttl: int = 3600
    memory_session_summary_ttl: int = 86400
    memory_session_summary_db_ttl: int = 604800
    memory_profile_redis_ttl: int = 3600

    # 记忆检索
    memory_search_top_k: int = 10
    memory_search_min_similarity: float = 0.75
    memory_hybrid_alpha: float = 0.5
    memory_hybrid_beta: float = 0.3
    memory_hybrid_gamma: float = 0.2

    # 上下文组装 Token 预算分配
    memory_assemble_system_ratio: float = 0.30
    memory_assemble_profile_ratio: float = 0.30
    memory_assemble_episodic_ratio: float = 0.30
    memory_assemble_buffer_ratio: float = 0.10
    memory_assemble_token_budget: int = 4096

    # L0 缓存
    memory_l0_max_size: int = 256

    # 熔断器
    memory_cb_failure_threshold: int = 5
    memory_cb_timeout_seconds: int = 60
    memory_cb_half_open_limit: int = 3

    # A/B 测试框架
    memory_ab_enabled: bool = False
    memory_ab_group: str = ""  # control | experiment


settings = Settings()
