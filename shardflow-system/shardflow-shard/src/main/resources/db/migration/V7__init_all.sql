-- ============================================================
-- ShardFlow Database Initialization (MySQL 8.0)
-- All tables, indexes, and seed data
-- Migrated from PostgreSQL + pgvector → MySQL + Milvus
-- ============================================================

-- =============================================================
-- 1. shardflow_user — 用户认证
-- =============================================================
CREATE TABLE IF NOT EXISTS shardflow_user (
    id              VARCHAR(36)  NOT NULL PRIMARY KEY,
    username        VARCHAR(128) NOT NULL,
    password_hash   VARCHAR(256) NOT NULL,
    user_id         VARCHAR(64)  NOT NULL,
    role            VARCHAR(32)  NOT NULL DEFAULT 'USER',
    enabled         TINYINT(1)   NOT NULL DEFAULT 1,
    created_at      DATETIME(3)  NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
    UNIQUE KEY uk_username (username),
    INDEX idx_user_user (user_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- =============================================================
-- 2. shardflow_shard — ContextShard 状态包
-- =============================================================
CREATE TABLE IF NOT EXISTS shardflow_shard (
    id                VARCHAR(36)  NOT NULL PRIMARY KEY,
    user_id           VARCHAR(64)  NOT NULL,
    task_id           VARCHAR(128) NOT NULL,
    session_seq       INT          NOT NULL DEFAULT 0,
    task_type         VARCHAR(50),
    task_goal         TEXT,
    knowledge_state   JSON,
    user_context      JSON,
    execution_state   JSON,
    confirmed         JSON         NOT NULL,
    excluded          JSON         NOT NULL,
    pending           JSON         NOT NULL,
    source_preference JSON,
    exploration_depth VARCHAR(32),
    key_decisions     JSON,
    version           INT          NOT NULL DEFAULT 1,
    status            VARCHAR(16)  NOT NULL DEFAULT 'SHARDED',
    created_at        DATETIME(3)  NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
    updated_at        DATETIME(3)  NOT NULL DEFAULT CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3),
    INDEX idx_shard_user_task (user_id, task_id),
    INDEX idx_shard_task_ver (task_id, version DESC)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- =============================================================
-- 3. shardflow_strategy — 策略记录（embedding 已迁移至 Milvus）
-- =============================================================
CREATE TABLE IF NOT EXISTS shardflow_strategy (
    strategy_id     VARCHAR(128) NOT NULL PRIMARY KEY,
    user_id         VARCHAR(64)  NOT NULL,
    task_type       VARCHAR(64)  NOT NULL,
    query_pattern   VARCHAR(1024),
    source_combo    JSON,
    success_score   DOUBLE       DEFAULT 0.0,
    cost_ms         INT          DEFAULT 0,
    created_at      DATETIME(3)  NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
    INDEX idx_strategy_user_type (user_id, task_type)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- =============================================================
-- 4. shardflow_task — 任务管理
-- =============================================================
CREATE TABLE IF NOT EXISTS shardflow_task (
    task_id         VARCHAR(128) NOT NULL PRIMARY KEY,
    user_id         VARCHAR(64)  NOT NULL,
    title           VARCHAR(512),
    description     TEXT,
    status          VARCHAR(32)  NOT NULL DEFAULT 'PENDING',
    session_id      VARCHAR(128),
    created_at      DATETIME(3)  NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
    updated_at      DATETIME(3)  NOT NULL DEFAULT CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3),
    INDEX idx_task_user (user_id),
    INDEX idx_task_status (status)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- =============================================================
-- 5. shardflow_user_profile — 用户画像
-- =============================================================
CREATE TABLE IF NOT EXISTS shardflow_user_profile (
    user_id     VARCHAR(64)  NOT NULL PRIMARY KEY,
    preferences JSON,
    expertise   JSON,
    habits      JSON,
    updated_at  DATETIME(3)  NOT NULL DEFAULT CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- =============================================================
-- 6. shardflow_mcp_tool — MCP 工具注册中心
-- =============================================================
CREATE TABLE IF NOT EXISTS shardflow_mcp_tool (
    tool_id           VARCHAR(128) NOT NULL PRIMARY KEY,
    tool_name         VARCHAR(128) NOT NULL,
    description       TEXT,
    mcp_server_url    VARCHAR(512),
    input_schema      JSON,
    output_schema     JSON,
    permissions       JSON,
    version           VARCHAR(32),
    status            VARCHAR(16)  NOT NULL DEFAULT 'ACTIVE',
    last_health_check DATETIME(3)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- =============================================================
-- 7. shardflow_audit_log — 审计日志
-- =============================================================
CREATE TABLE IF NOT EXISTS shardflow_audit_log (
    id              BIGINT       NOT NULL AUTO_INCREMENT PRIMARY KEY,
    user_id         VARCHAR(64)  NOT NULL,
    tool_name       VARCHAR(128),
    params_summary  VARCHAR(512),
    success         TINYINT(1)   NOT NULL DEFAULT 0,
    error           TEXT,
    latency_ms      BIGINT       DEFAULT 0,
    created_at      DATETIME(3)  NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
    INDEX idx_audit_user (user_id),
    INDEX idx_audit_created (created_at DESC)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- =============================================================
-- 8. shardflow_task_session — 任务多会话追踪
-- =============================================================
CREATE TABLE IF NOT EXISTS shardflow_task_session (
    id          BIGINT       NOT NULL AUTO_INCREMENT PRIMARY KEY,
    task_id     VARCHAR(128) NOT NULL,
    user_id     VARCHAR(64)  NOT NULL,
    session_seq INT          NOT NULL DEFAULT 0,
    source_port VARCHAR(16),
    status      VARCHAR(16)  NOT NULL DEFAULT 'ACTIVE',
    created_at  DATETIME(3)  NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
    INDEX idx_ts_task (task_id),
    INDEX idx_ts_user (user_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- =============================================================
-- 默认策略种子数据（冷启动回退）
-- =============================================================
INSERT IGNORE INTO shardflow_strategy (strategy_id, user_id, task_type, query_pattern, source_combo, success_score, cost_ms)
VALUES
    ('default-dependency', 'system', 'dependency_chain_analysis',
     'Trace service call dependencies',
     '[{"source":"code_comments","weight":0.6,"reliability":0.8},{"source":"github_issues","weight":0.2,"reliability":0.6},{"source":"official_doc","weight":0.2,"reliability":0.9}]',
     0.8, 3000),
    ('default-exploration', 'system', 'general_code_exploration',
     'Explore codebase structure',
     '[{"source":"code_comments","weight":0.4,"reliability":0.7},{"source":"official_doc","weight":0.3,"reliability":0.9},{"source":"stackoverflow","weight":0.3,"reliability":0.6}]',
     0.75, 2000),
    ('default-troubleshooting', 'system', 'error_troubleshooting',
     'Debug errors and exceptions',
     '[{"source":"stackoverflow","weight":0.4,"reliability":0.7},{"source":"github_issues","weight":0.4,"reliability":0.6},{"source":"official_doc","weight":0.2,"reliability":0.9}]',
     0.7, 4000);
