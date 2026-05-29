-- ============================================================
-- ShardFlow V5: ContextShard schema upgrade
-- Add knowledge_state, user_context, execution_state columns
-- ============================================================

ALTER TABLE shardflow_shard
    ADD COLUMN IF NOT EXISTS task_type VARCHAR(50),
    ADD COLUMN IF NOT EXISTS task_goal TEXT,
    ADD COLUMN IF NOT EXISTS knowledge_state JSONB,
    ADD COLUMN IF NOT EXISTS user_context JSONB,
    ADD COLUMN IF NOT EXISTS execution_state JSONB;

-- GIN index for knowledge_state JSONB queries
CREATE INDEX IF NOT EXISTS idx_shard_ks ON shardflow_shard USING GIN (knowledge_state);

-- GIN index for user_context JSONB queries
CREATE INDEX IF NOT EXISTS idx_shard_uc ON shardflow_shard USING GIN (user_context);
