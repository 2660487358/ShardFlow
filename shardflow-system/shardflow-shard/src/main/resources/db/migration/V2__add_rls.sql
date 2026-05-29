-- ============================================================
-- ShardFlow V2: Row-Level Security for User Isolation
-- Enables PostgreSQL RLS on all user-data tables so that
-- the database itself enforces user-level data isolation.
-- ============================================================

-- -----------------------------------------------------------
-- Enable RLS on all user data tables
-- -----------------------------------------------------------
ALTER TABLE shardflow_shard    ENABLE ROW LEVEL SECURITY;
ALTER TABLE shardflow_strategy ENABLE ROW LEVEL SECURITY;
ALTER TABLE shardflow_task     ENABLE ROW LEVEL SECURITY;
ALTER TABLE shardflow_user     ENABLE ROW LEVEL SECURITY;

-- -----------------------------------------------------------
-- RLS Policies: each user can only see/operate on their own rows
-- Policy uses current_setting('app.current_user') which must be set
-- by the application at the start of each DB session/transaction.
-- -----------------------------------------------------------

-- shardflow_shard policy
DROP POLICY IF EXISTS shard_user_isolation ON shardflow_shard;
CREATE POLICY shard_user_isolation ON shardflow_shard
    FOR ALL
    USING (user_id = current_setting('app.current_user')::varchar)
    WITH CHECK (user_id = current_setting('app.current_user')::varchar);

-- shardflow_strategy policy
DROP POLICY IF EXISTS strategy_user_isolation ON shardflow_strategy;
CREATE POLICY strategy_user_isolation ON shardflow_strategy
    FOR ALL
    USING (user_id = current_setting('app.current_user')::varchar)
    WITH CHECK (user_id = current_setting('app.current_user')::varchar);

-- shardflow_task policy
DROP POLICY IF EXISTS task_user_isolation ON shardflow_task;
CREATE POLICY task_user_isolation ON shardflow_task
    FOR ALL
    USING (user_id = current_setting('app.current_user')::varchar)
    WITH CHECK (user_id = current_setting('app.current_user')::varchar);

-- shardflow_user policy: each user can read/update their own row
-- Note: users with role='ADMIN' may need a separate bypass policy in the future
DROP POLICY IF EXISTS user_self_isolation ON shardflow_user;
CREATE POLICY user_self_isolation ON shardflow_user
    FOR ALL
    USING (user_id = current_setting('app.current_user')::varchar)
    WITH CHECK (user_id = current_setting('app.current_user')::varchar);

-- -----------------------------------------------------------
-- Helper function: set current user for the session
-- The application MUST call this at the beginning of each
-- transactional context (e.g., in a Spring Filter or Interceptor).
--
-- Usage: SELECT set_app_user('user-123');
-- -----------------------------------------------------------
CREATE OR REPLACE FUNCTION set_app_user(uid varchar) RETURNS void AS $$
BEGIN
    PERFORM set_config('app.current_user', uid, false);
END;
$$ LANGUAGE plpgsql;
