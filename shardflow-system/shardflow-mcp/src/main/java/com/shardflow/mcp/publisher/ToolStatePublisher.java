package com.shardflow.mcp.publisher;

import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.shardflow.common.config.McpRedisConstants;
import com.shardflow.common.entity.McpToolEntity;
import com.shardflow.usercontext.context.UserContext;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.data.redis.core.RedisTemplate;
import org.springframework.stereotype.Component;

import java.time.Instant;
import java.util.Map;

/**
 * 工具状态发布器.
 * 实现状态变更后 Redis Hash 写入 + TTL 刷新 + 唤醒信号发布 (FR-STATUS-003).
 *
 * <p>写入流程：
 * <ol>
 *   <li>HSET 更新 Hash 中对应工具字段</li>
 *   <li>EXPIRE 刷新 Hash TTL（30s）</li>
 *   <li>PUBLISH 轻量唤醒信号</li>
 * </ol>
 */
@Slf4j
@Component
@RequiredArgsConstructor
public class ToolStatePublisher {

    private final RedisTemplate<String, Object> redisTemplate;
    private final ObjectMapper objectMapper;

    /**
     * 发布工具状态变更到 Redis Hash + 唤醒信号.
     *
     * @param tool 变更后的工具实体
     */
    public void publishStateChange(McpToolEntity tool) {
        String userId = tool.getUserId();
        if (userId == null || userId.isBlank()) {
            userId = UserContext.getUserId();
        }
        String hashKey = McpRedisConstants.toolStatesKey(userId);
        String wakeupChannel = McpRedisConstants.wakeupChannel(userId);

        try {
            // 构建状态快照 JSON
            Map<String, Object> stateSnapshot = Map.of(
                "status", tool.getStatus(),
                "health", tool.getHealthStatus() != null ? tool.getHealthStatus() : "UNKNOWN",
                "version", tool.getVersion() != null ? tool.getVersion() : "1.0.0",
                "updated_at", Instant.now().toString()
            );
            String stateJson = objectMapper.writeValueAsString(stateSnapshot);

            // HSET 更新 Hash 中对应工具字段
            redisTemplate.opsForHash().put(hashKey, tool.getToolId(), stateJson);

            // EXPIRE 刷新 Hash TTL
            redisTemplate.expire(hashKey, java.time.Duration.ofSeconds(McpRedisConstants.TOOL_STATES_TTL_SECONDS));

            // PUBLISH 轻量唤醒信号
            redisTemplate.convertAndSend(wakeupChannel, McpRedisConstants.WAKEUP_MESSAGE);

            log.debug("Published state change for tool {}: {} -> Hash key: {}",
                tool.getToolId(), tool.getStatus(), hashKey);
        } catch (JsonProcessingException e) {
            log.error("Failed to serialize tool state for publishing: toolId={}", tool.getToolId(), e);
        }
    }

    /**
     * 从 Hash 中移除工具状态（软删除时使用）.
     *
     * @param tool 被删除的工具实体
     */
    public void removeToolState(McpToolEntity tool) {
        String userId = tool.getUserId();
        if (userId == null || userId.isBlank()) {
            userId = UserContext.getUserId();
        }
        String hashKey = McpRedisConstants.toolStatesKey(userId);
        String wakeupChannel = McpRedisConstants.wakeupChannel(userId);

        // HDEL 移除 Hash 中对应 field
        redisTemplate.opsForHash().delete(hashKey, tool.getToolId());

        // EXPIRE 刷新 Hash TTL
        redisTemplate.expire(hashKey, java.time.Duration.ofSeconds(McpRedisConstants.TOOL_STATES_TTL_SECONDS));

        // PUBLISH 轻量唤醒信号
        redisTemplate.convertAndSend(wakeupChannel, McpRedisConstants.WAKEUP_MESSAGE);

        log.debug("Removed tool state from Hash: toolId={}, hashKey={}", tool.getToolId(), hashKey);
    }
}
