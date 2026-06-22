package com.shardflow.common.config;

/**
 * Skills 管理 Redis 缓存常量与 Key 规范定义.
 *
 * <p>Per Skills管理需求规格文档 FR-9 / 实施计划 P1.3.1.
 * <p>缓存策略（D-6）：
 * <ul>
 *   <li>L1 Python 内存（会话级）</li>
 *   <li>L2 Redis skill_meta:* （TTL 5 分钟，Java 端写入，Python 端读取）</li>
 *   <li>L3 MinIO（长期 Artifact）</li>
 * </ul>
 *
 * <p>Key 命名遵循现有 McpRedisConstants 模式，带 user_id 隔离前缀：
 * <ul>
 *   <li>shardflow:{user_id}:skill:meta:{skill_code} — Skill 元数据，TTL 5 分钟</li>
 *   <li>shardflow:{user_id}:skill:index:{agent_id} — Agent 挂载索引，TTL 5 分钟</li>
 *   <li>shardflow:{user_id}:skill:list — Skill 列表缓存，TTL 5 分钟</li>
 * </ul>
 *
 * <p>失效策略（FR-9）：Skill 状态变更、版本发布后由 SkillCacheEvictor 主动失效对应 Key。
 */
public final class SkillRedisConstants {

    private SkillRedisConstants() {}

    // ======================== Key 前缀 ========================

    private static final String SKILL_PREFIX = "shardflow:%s:skill:";

    // ======================== 缓存 Key ========================

    /**
     * 单个 Skill 元数据缓存 Key.
     * String(JSON)，TTL = 5min
     * 存储 Skill 完整元数据（含 schema/trigger_keywords/cost_estimate 等）
     */
    public static final String SKILL_META_KEY = SKILL_PREFIX + "meta:%s";

    /** Skill 元数据缓存 TTL（秒） */
    public static final long SKILL_META_TTL_SECONDS = 300;

    /**
     * Agent 挂载 Skill 索引缓存 Key.
     * String(JSON)，TTL = 5min
     * 存储该 Agent 绑定的 Skill 列表（含 binding_type/priority/config_override）
     */
    public static final String SKILL_INDEX_KEY = SKILL_PREFIX + "index:%s";

    /** Agent 挂载索引缓存 TTL（秒） */
    public static final long SKILL_INDEX_TTL_SECONDS = 300;

    /**
     * 用户 Skill 列表缓存 Key.
     * String(JSON)，TTL = 5min
     * 存储用户可见的 Skill 列表（含筛选条件 hash）
     */
    public static final String SKILL_LIST_KEY = SKILL_PREFIX + "list";

    /** Skill 列表缓存 TTL（秒） */
    public static final long SKILL_LIST_TTL_SECONDS = 300;

    /**
     * Skill 分类列表缓存 Key.
     * String(JSON)，TTL = 30min
     * 分类列表变更频率低，TTL 较长
     */
    public static final String SKILL_CATEGORIES_KEY = SKILL_PREFIX + "categories";

    /** 分类列表缓存 TTL（秒） */
    public static final long SKILL_CATEGORIES_TTL_SECONDS = 1800;

    // ======================== 工具方法 ========================

    /**
     * 构建单个 Skill 元数据缓存 Key.
     * @param userId   用户ID
     * @param skillCode Skill 编码
     * @return shardflow:{userId}:skill:meta:{skillCode}
     */
    public static String skillMetaKey(String userId, String skillCode) {
        return String.format(SKILL_META_KEY, userId, skillCode);
    }

    /**
     * 构建 Agent 挂载索引缓存 Key.
     * @param userId  用户ID
     * @param agentId Agent 编码
     * @return shardflow:{userId}:skill:index:{agentId}
     */
    public static String skillIndexKey(String userId, String agentId) {
        return String.format(SKILL_INDEX_KEY, userId, agentId);
    }

    /**
     * 构建用户 Skill 列表缓存 Key.
     * @param userId 用户ID
     * @return shardflow:{userId}:skill:list
     */
    public static String skillListKey(String userId) {
        return String.format(SKILL_LIST_KEY, userId);
    }

    /**
     * 构建分类列表缓存 Key.
     * @param userId 用户ID
     * @return shardflow:{userId}:skill:categories
     */
    public static String skillCategoriesKey(String userId) {
        return String.format(SKILL_CATEGORIES_KEY, userId);
    }
}
