-- ============================================================
-- ShardFlow Skills 管理 — 补充 Skill 配置字段与 current_version 默认值 (P3)
-- 版本: V2
-- 关联需求: FR-3.5 / P3-ISSUE-001
-- 说明:
--   P1/P2 阶段 CreateSkillRequest 已包含 config 字段，但 skill_registry 表未同步；
--   同时 current_version NOT NULL 且无默认值，导致创建 draft Skill 时触发约束错误。
-- 前置条件: V1__skill_management.sql 已执行
-- 幂等性: 使用 IF NOT EXISTS / DROP DEFAULT IF EXISTS 保证可重复执行
-- ============================================================

-- 1. 为 current_version 补充默认值，避免 draft 状态插入失败
DO $$
BEGIN
    -- 仅当当前无默认值时附加默认值
    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = current_schema()
          AND table_name   = 'skill_registry'
          AND column_name  = 'current_version'
          AND column_default IS NULL
    ) THEN
        ALTER TABLE skill_registry
            ALTER COLUMN current_version SET DEFAULT '';

        -- 对历史空值进行兜底填充（不应影响已有非空数据）
        UPDATE skill_registry
        SET current_version = ''
        WHERE current_version IS NULL;
    END IF;
END $$;

-- 2. 新增 config 字段，存储 Skill 运行配置 JSON
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = current_schema()
          AND table_name   = 'skill_registry'
          AND column_name  = 'config'
    ) THEN
        ALTER TABLE skill_registry
            ADD COLUMN config JSONB;

        COMMENT ON COLUMN skill_registry.config IS 'Skill 运行配置，JSONB格式';
    END IF;
END $$;