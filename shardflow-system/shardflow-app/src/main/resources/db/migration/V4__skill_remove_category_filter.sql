-- ============================================================
-- ShardFlow Skills 管理 — 移除分类筛选字段与筛选索引 (P1)
-- 版本: V4
-- 关联需求: Skill 模块端到端改造 — 移除分类/信任等级/执行模式筛选条件
-- 设计决策:
--   1. category 字段彻底移除（仅用于筛选，无其他业务依赖）
--   2. trust_tier / skill_type 字段保留（有核心业务依赖：可见性规则、执行器路由）
--   3. trust_tier 索引保留（可见性查询 WHERE trust_tier='official' 仍需使用）
--   4. 仅移除 category 列和 category 索引
-- ============================================================

-- 移除 category 筛选索引
DROP INDEX IF EXISTS idx_skill_registry_category;

-- 移除 category 列
ALTER TABLE skill_registry DROP COLUMN IF EXISTS category;

-- 移除 category 列注释（如果存在）
COMMENT ON COLUMN skill_registry.category IS NULL;
