-- ============================================================
-- ShardFlow Database Initialization
-- Phase 2: Schema creation, pgvector extension, core tables
-- ============================================================

-- Enable pgvector extension for semantic search
CREATE EXTENSION IF NOT EXISTS vector;

-- Create schema for user isolation
CREATE SCHEMA IF NOT EXISTS shardflow_shared;

-- -----------------------------------------------------------
-- shardflow_shard: Context shard storage with versioning
-- -----------------------------------------------------------
CREATE TABLE IF NOT EXISTS shardflow_shard (
    id              VARCHAR(36)  PRIMARY KEY,
    user_id         VARCHAR(64)  NOT NULL,
    task_id         VARCHAR(128) NOT NULL,
    session_seq     INT          NOT NULL DEFAULT 0,
    confirmed       JSONB        NOT NULL DEFAULT '[]',
    excluded        JSONB        NOT NULL DEFAULT '[]',
    pending         JSONB        NOT NULL DEFAULT '[]',
    source_preference JSONB,
    exploration_depth VARCHAR(32),
    key_decisions   JSONB,
    version         INT          NOT NULL DEFAULT 1,
    status          VARCHAR(16)  NOT NULL DEFAULT 'SHARDED',
    created_at      TIMESTAMPTZ  NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ  NOT NULL DEFAULT now()
);

CREATE INDEX idx_shard_user_task ON shardflow_shard(user_id, task_id);
CREATE INDEX idx_shard_task_version ON shardflow_shard(task_id, version DESC);

-- -----------------------------------------------------------
-- shardflow_strategy: Strategy records with embedding for pgvector search
-- -----------------------------------------------------------
CREATE TABLE IF NOT EXISTS shardflow_strategy (
    strategy_id     VARCHAR(128) PRIMARY KEY,
    user_id         VARCHAR(64)  NOT NULL,
    task_type       VARCHAR(64)  NOT NULL,
    query_pattern   VARCHAR(1024),
    source_combo    JSONB,
    success_score   DOUBLE PRECISION DEFAULT 0.0,
    cost_ms         INT          DEFAULT 0,
    embedding       vector(1536),
    created_at      TIMESTAMPTZ  NOT NULL DEFAULT now()
);

CREATE INDEX idx_strategy_user_type ON shardflow_strategy(user_id, task_type);
CREATE INDEX idx_strategy_embedding ON shardflow_strategy USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);

-- -----------------------------------------------------------
-- shardflow_task: Task management
-- -----------------------------------------------------------
CREATE TABLE IF NOT EXISTS shardflow_task (
    task_id         VARCHAR(128) PRIMARY KEY,
    user_id         VARCHAR(64)  NOT NULL,
    title           VARCHAR(512),
    description     TEXT,
    status          VARCHAR(32)  NOT NULL DEFAULT 'PENDING',
    session_id      VARCHAR(128),
    created_at      TIMESTAMPTZ  NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ  NOT NULL DEFAULT now()
);

CREATE INDEX idx_task_user ON shardflow_task(user_id);
CREATE INDEX idx_task_status ON shardflow_task(status);

-- -----------------------------------------------------------
-- shardflow_user: User authentication
-- -----------------------------------------------------------
CREATE TABLE IF NOT EXISTS shardflow_user (
    id              VARCHAR(36)  PRIMARY KEY,
    username        VARCHAR(128) NOT NULL UNIQUE,
    password_hash   VARCHAR(256) NOT NULL,
    user_id         VARCHAR(64)  NOT NULL,
    role            VARCHAR(32)  NOT NULL DEFAULT 'USER',
    enabled         BOOLEAN      NOT NULL DEFAULT true,
    created_at      TIMESTAMPTZ  NOT NULL DEFAULT now()
);

CREATE INDEX idx_user_user ON shardflow_user(user_id);
CREATE INDEX idx_user_username ON shardflow_user(username);

-- -----------------------------------------------------------
-- Insert default strategies for cold-start scenarios
-- -----------------------------------------------------------
INSERT INTO shardflow_strategy (strategy_id, user_id, task_type, query_pattern, source_combo, success_score, cost_ms)
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
