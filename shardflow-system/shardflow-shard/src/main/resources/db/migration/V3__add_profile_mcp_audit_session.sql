-- ============================================================
-- ShardFlow V3: Additional tables for profile, MCP tools,
-- audit log, and task sessions
-- ============================================================

-- shardflow_user_profile: User preference/profile storage
CREATE TABLE IF NOT EXISTS shardflow_user_profile (
    user_id     VARCHAR(64)  PRIMARY KEY,
    preferences JSONB,
    expertise   JSONB,
    habits      JSONB,
    updated_at  TIMESTAMPTZ  NOT NULL DEFAULT now()
);

-- shardflow_mcp_tool: MCP tool registry
CREATE TABLE IF NOT EXISTS shardflow_mcp_tool (
    tool_id           VARCHAR(128) PRIMARY KEY,
    tool_name         VARCHAR(128) NOT NULL,
    description       TEXT,
    mcp_server_url    VARCHAR(512),
    input_schema      JSONB,
    output_schema     JSONB,
    permissions       JSONB,
    version           VARCHAR(32),
    status            VARCHAR(16)  NOT NULL DEFAULT 'ACTIVE',
    last_health_check TIMESTAMPTZ
);

-- shardflow_audit_log: Tool call audit trail
CREATE TABLE IF NOT EXISTS shardflow_audit_log (
    id              BIGSERIAL PRIMARY KEY,
    user_id         VARCHAR(64)  NOT NULL,
    tool_name       VARCHAR(128),
    params_summary  VARCHAR(512),
    success         BOOLEAN      NOT NULL DEFAULT false,
    error           TEXT,
    latency_ms      BIGINT       DEFAULT 0,
    created_at      TIMESTAMPTZ  NOT NULL DEFAULT now()
);

CREATE INDEX idx_audit_user ON shardflow_audit_log(user_id);
CREATE INDEX idx_audit_created ON shardflow_audit_log(created_at DESC);

-- shardflow_task_session: Task multi-session tracking
CREATE TABLE IF NOT EXISTS shardflow_task_session (
    id          BIGSERIAL PRIMARY KEY,
    task_id     VARCHAR(128) NOT NULL,
    user_id     VARCHAR(64)  NOT NULL,
    session_seq INT          NOT NULL DEFAULT 0,
    source_port VARCHAR(16),
    status      VARCHAR(16)  NOT NULL DEFAULT 'ACTIVE',
    created_at  TIMESTAMPTZ  NOT NULL DEFAULT now()
);

CREATE INDEX idx_ts_task ON shardflow_task_session(task_id);
CREATE INDEX idx_ts_user ON shardflow_task_session(user_id);
