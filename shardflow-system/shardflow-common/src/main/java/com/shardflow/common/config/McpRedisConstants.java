package com.shardflow.common.config;

/**
 * MCP 管理 Redis 缓存常量与 Key 规范定义.
 *
 * <p>Per MCP管理需求规格文档 section 6.3:
 * <ul>
 *   <li>Hash 状态存储: shardflow:{user_id}:mcp:tool_states (唯一真相源)</li>
 *   <li>轻量唤醒通道: shardflow:{user_id}:mcp:wakeup (Pub/Sub)</li>
 *   <li>缓存 Key: tools:list / tool:{tool_id} / tools:discover</li>
 * </ul>
 *
 * <p>状态同步模型 (spec section 5.3):
 * <ul>
 *   <li>Java 端写入: HSET + EXPIRE + PUBLISH 唤醒</li>
 *   <li>Python 端读取: 启动 HGETALL + 唤醒触发 HGETALL + 30s 定时 HGETALL 兜底</li>
 * </ul>
 *
 * <p>降级策略 (spec section 5.3.4):
 * <ul>
 *   <li>HGETALL 返回空 → Java 端失联 → 降级至 L0 本地缓存 + 告警</li>
 *   <li>Redis 不可用 → 降级至 L0 缓存 + HTTP 全量兜底</li>
 * </ul>
 */
public final class McpRedisConstants {

    private McpRedisConstants() {}

    // ======================== Key 前缀 ========================

    private static final String MCP_PREFIX = "shardflow:%s:mcp:";

    // ======================== Hash 状态存储 ========================

    /**
     * 工具状态 Hash Key.
     * field = tool_id, value = JSON{status, health, version, updated_at}
     * TTL = 30s（Java 端心跳每 10s 刷新）
     */
    public static final String TOOL_STATES_HASH = MCP_PREFIX + "tool_states";

    /** Hash 状态存储 TTL（秒） */
    public static final long TOOL_STATES_TTL_SECONDS = 30;

    /** Java 端心跳刷新间隔（毫秒） */
    public static final long HEARTBEAT_INTERVAL_MS = 10_000;

    // ======================== 轻量唤醒通道 ========================

    /**
     * 唤醒信号 Pub/Sub 通道.
     * 消息体仅 "1"，不承载业务数据，仅触发 Python 端 HGETALL 拉取
     */
    public static final String WAKEUP_CHANNEL = MCP_PREFIX + "wakeup";

    /** 唤醒信号消息体 */
    public static final String WAKEUP_MESSAGE = "1";

    // ======================== 缓存 Key ========================

    /**
     * 用户可用工具列表缓存 Key.
     * String(JSON)，TTL = 5min
     */
    public static final String TOOLS_LIST_KEY = MCP_PREFIX + "tools:list";

    /** 工具列表缓存 TTL（秒） */
    public static final long TOOLS_LIST_TTL_SECONDS = 300;

    /**
     * 单个工具完整元数据缓存 Key.
     * String(JSON)，TTL = 10min
     */
    public static final String TOOL_DETAIL_KEY = MCP_PREFIX + "tool:%s";

    /** 工具详情缓存 TTL（秒） */
    public static final long TOOL_DETAIL_TTL_SECONDS = 600;

    /**
     * 工具发现快照缓存 Key（Python 推理层专用）.
     * String(JSON)，TTL = 5min
     */
    public static final String TOOLS_DISCOVER_KEY = MCP_PREFIX + "tools:discover";

    /** 工具发现缓存 TTL（秒） */
    public static final long TOOLS_DISCOVER_TTL_SECONDS = 300;

    // ======================== 健康检查 ========================

    /** 健康检查间隔（毫秒） */
    public static final long HEALTH_CHECK_INTERVAL_MS = 10_000;

    /** 连续失败次数阈值（达到后标记 INACTIVE） */
    public static final int HEALTH_CHECK_FAILURE_THRESHOLD = 3;

    /** 连续成功次数阈值（达到后恢复 ACTIVE） */
    public static final int HEALTH_CHECK_SUCCESS_THRESHOLD = 3;

    // ======================== Python 端轮询 ========================

    /** Python 端定时轮询间隔（毫秒） */
    public static final long PYTHON_POLL_INTERVAL_MS = 30_000;

    // ======================== 工具方法 ========================

    /**
     * 构建工具状态 Hash Key.
     * @param userId 用户ID
     * @return shardflow:{userId}:mcp:tool_states
     */
    public static String toolStatesKey(String userId) {
        return String.format(TOOL_STATES_HASH, userId);
    }

    /**
     * 构建唤醒信号通道名.
     * @param userId 用户ID
     * @return shardflow:{userId}:mcp:wakeup
     */
    public static String wakeupChannel(String userId) {
        return String.format(WAKEUP_CHANNEL, userId);
    }

    /**
     * 构建工具列表缓存 Key.
     * @param userId 用户ID
     * @return shardflow:{userId}:mcp:tools:list
     */
    public static String toolsListKey(String userId) {
        return String.format(TOOLS_LIST_KEY, userId);
    }

    /**
     * 构建工具详情缓存 Key.
     * @param userId 用户ID
     * @param toolId 工具ID
     * @return shardflow:{userId}:mcp:tool:{toolId}
     */
    public static String toolDetailKey(String userId, String toolId) {
        return String.format(TOOL_DETAIL_KEY, userId, toolId);
    }

    /**
     * 构建工具发现快照缓存 Key.
     * @param userId 用户ID
     * @return shardflow:{userId}:mcp:tools:discover
     */
    public static String toolsDiscoverKey(String userId) {
        return String.format(TOOLS_DISCOVER_KEY, userId);
    }
}
