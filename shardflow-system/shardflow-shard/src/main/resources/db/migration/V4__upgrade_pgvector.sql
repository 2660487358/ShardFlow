-- ============================================================
-- ShardFlow V4: pgvector embedding column upgrade
-- Convert embedding from String to native vector(1536)
-- ============================================================

-- Add a temporary column, migrate data, then swap
ALTER TABLE shardflow_strategy ADD COLUMN IF NOT EXISTS embedding_v2 vector(1536);

-- Create IVFFlat index for cosine similarity search
CREATE INDEX IF NOT EXISTS idx_strategy_embedding_v2 ON shardflow_strategy
    USING ivfflat (embedding_v2 vector_cosine_ops) WITH (lists = 100);
