-- ============================================================
-- ShardFlow V6: Row-Level Security on all user-data tables
-- ============================================================

ALTER TABLE shardflow_shard ENABLE ROW LEVEL SECURITY;
ALTER TABLE shardflow_strategy ENABLE ROW LEVEL SECURITY;
ALTER TABLE shardflow_task ENABLE ROW LEVEL SECURITY;
ALTER TABLE shardflow_user_profile ENABLE ROW LEVEL SECURITY;
ALTER TABLE shardflow_audit_log ENABLE ROW LEVEL SECURITY;
ALTER TABLE shardflow_task_session ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS rls_shard ON shardflow_shard;
CREATE POLICY rls_shard ON shardflow_shard
    FOR ALL USING (user_id = current_setting('app.current_user')::VARCHAR)
    WITH CHECK (user_id = current_setting('app.current_user')::VARCHAR);

DROP POLICY IF EXISTS rls_strategy ON shardflow_strategy;
CREATE POLICY rls_strategy ON shardflow_strategy
    FOR ALL USING (user_id = current_setting('app.current_user')::VARCHAR)
    WITH CHECK (user_id = current_setting('app.current_user')::VARCHAR);

DROP POLICY IF EXISTS rls_task ON shardflow_task;
CREATE POLICY rls_task ON shardflow_task
    FOR ALL USING (user_id = current_setting('app.current_user')::VARCHAR)
    WITH CHECK (user_id = current_setting('app.current_user')::VARCHAR);

DROP POLICY IF EXISTS rls_user_profile ON shardflow_user_profile;
CREATE POLICY rls_user_profile ON shardflow_user_profile
    FOR ALL USING (user_id = current_setting('app.current_user')::VARCHAR)
    WITH CHECK (user_id = current_setting('app.current_user')::VARCHAR);

DROP POLICY IF EXISTS rls_audit_log ON shardflow_audit_log;
CREATE POLICY rls_audit_log ON shardflow_audit_log
    FOR ALL USING (user_id = current_setting('app.current_user')::VARCHAR)
    WITH CHECK (user_id = current_setting('app.current_user')::VARCHAR);

DROP POLICY IF EXISTS rls_task_session ON shardflow_task_session;
CREATE POLICY rls_task_session ON shardflow_task_session
    FOR ALL USING (user_id = current_setting('app.current_user')::VARCHAR)
    WITH CHECK (user_id = current_setting('app.current_user')::VARCHAR);
