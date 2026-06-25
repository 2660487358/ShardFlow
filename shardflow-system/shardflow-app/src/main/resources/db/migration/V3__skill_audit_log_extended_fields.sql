-- ============================================================
-- ShardFlow Skills 管理 — 审计日志扩展字段 (P6)
-- 版本: V3
-- 关联需求: FR-8.7 / FR-8.8 / P6.4 / P6.5
-- 说明:
--   P6 阶段审计日志需记录调用性能指标（latency_ms / tokens_used）
--   与执行结果（success / error），以支持成本归因分析。
--   原 skill_audit_log 表缺少这些字段，本脚本补充。
-- 前置条件: V1__skill_management.sql 已执行
-- 幂等性: 使用 IF NOT EXISTS 保证可重复执行
-- ============================================================

-- 1. 新增 latency_ms 字段，记录调用延迟（毫秒）
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = current_schema()
          AND table_name   = 'skill_audit_log'
          AND column_name  = 'latency_ms'
    ) THEN
        ALTER TABLE skill_audit_log
            ADD COLUMN latency_ms INTEGER DEFAULT 0;

        COMMENT ON COLUMN skill_audit_log.latency_ms IS '调用延迟（毫秒）';
    END IF;
END $$;

-- 2. 新增 tokens_used 字段，记录 Token 消耗
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = current_schema()
          AND table_name   = 'skill_audit_log'
          AND column_name  = 'tokens_used'
    ) THEN
        ALTER TABLE skill_audit_log
            ADD COLUMN tokens_used INTEGER DEFAULT 0;

        COMMENT ON COLUMN skill_audit_log.tokens_used IS 'Token 消耗（input + output）';
    END IF;
END $$;

-- 3. 新增 success 字段，记录执行是否成功
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = current_schema()
          AND table_name   = 'skill_audit_log'
          AND column_name  = 'success'
    ) THEN
        ALTER TABLE skill_audit_log
            ADD COLUMN success BOOLEAN DEFAULT TRUE;

        COMMENT ON COLUMN skill_audit_log.success IS '执行是否成功';
    END IF;
END $$;

-- 4. 新增 error 字段，记录错误信息
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = current_schema()
          AND table_name   = 'skill_audit_log'
          AND column_name  = 'error'
    ) THEN
        ALTER TABLE skill_audit_log
            ADD COLUMN error TEXT;

        COMMENT ON COLUMN skill_audit_log.error IS '错误信息（失败时记录）';
    END IF;
END $$;

-- 5. 新增 session_id 字段，记录会话ID（用于关联对话上下文）
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = current_schema()
          AND table_name   = 'skill_audit_log'
          AND column_name  = 'session_id'
    ) THEN
        ALTER TABLE skill_audit_log
            ADD COLUMN session_id VARCHAR(64);

        COMMENT ON COLUMN skill_audit_log.session_id IS '会话ID（执行调用时记录）';

        CREATE INDEX IF NOT EXISTS idx_skill_audit_session ON skill_audit_log (session_id);
    END IF;
END $$;
