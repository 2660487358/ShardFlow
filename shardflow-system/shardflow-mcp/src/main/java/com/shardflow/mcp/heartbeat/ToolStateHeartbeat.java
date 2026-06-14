package com.shardflow.mcp.heartbeat;

import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.shardflow.common.config.McpRedisConstants;
import com.shardflow.common.entity.McpToolEntity;
import com.shardflow.mcp.repository.McpToolRepository;
import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.data.redis.core.RedisTemplate;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;

import java.time.Duration;
import java.time.Instant;
import java.util.List;
import java.util.Map;

/**
 * Java 端心跳定时器.
 * 每 10s 定时 HSET Hash + EXPIRE 刷新 TTL，维持 Key 存活 (FR-HEALTH-005).
 * 同时检测 Hash Key 是否意外过期，若不存在则从 MySQL 重建.
 */
@Slf4j
@Component
@RequiredArgsConstructor
public class ToolStateHeartbeat {

    private final McpToolRepository repository;
    private final RedisTemplate<String, Object> redisTemplate;
    private final ObjectMapper objectMapper;

    /**
     * 心跳定时器：每 10s 刷新所有用户的 Hash TTL.
     * 若 Hash Key 不存在（被删除或 Redis 重启），从 MySQL 重建.
     */
    @Scheduled(fixedRate = McpRedisConstants.HEARTBEAT_INTERVAL_MS, initialDelay = 5000)
    public void heartbeat() {
        // 查询所有 ACTIVE 状态的工具（跨用户）
        List<McpToolEntity> activeTools = repository.selectList(
            new LambdaQueryWrapper<McpToolEntity>()
                .eq(McpToolEntity::getStatus, "ACTIVE")
        );

        if (activeTools.isEmpty()) {
            return;
        }

        // 按用户分组刷新
        Map<String, List<McpToolEntity>> toolsByUser = activeTools.stream()
            .collect(java.util.stream.Collectors.groupingBy(McpToolEntity::getUserId));

        for (Map.Entry<String, List<McpToolEntity>> entry : toolsByUser.entrySet()) {
            String userId = entry.getKey();
            List<McpToolEntity> tools = entry.getValue();
            String hashKey = McpRedisConstants.toolStatesKey(userId);

            try {
                // 检查 Hash Key 是否存在，不存在则重建
                Boolean exists = redisTemplate.hasKey(hashKey);
                if (exists == null || !exists) {
                    log.info("Hash key {} not found, rebuilding from MySQL", hashKey);
                    rebuildHash(hashKey, tools);
                } else {
                    // 仅刷新 TTL
                    redisTemplate.expire(hashKey, Duration.ofSeconds(McpRedisConstants.TOOL_STATES_TTL_SECONDS));
                }
            } catch (Exception e) {
                log.error("Heartbeat failed for user {}: {}", userId, e.getMessage());
            }
        }
    }

    /**
     * 从 MySQL 重建 Hash 状态快照.
     */
    private void rebuildHash(String hashKey, List<McpToolEntity> tools) {
        try {
            for (McpToolEntity tool : tools) {
                Map<String, Object> stateSnapshot = Map.of(
                    "status", tool.getStatus(),
                    "health", tool.getHealthStatus() != null ? tool.getHealthStatus() : "UNKNOWN",
                    "version", tool.getVersion() != null ? tool.getVersion() : "1.0.0",
                    "updated_at", Instant.now().toString()
                );
                String stateJson = objectMapper.writeValueAsString(stateSnapshot);
                redisTemplate.opsForHash().put(hashKey, tool.getToolId(), stateJson);
            }
            redisTemplate.expire(hashKey, Duration.ofSeconds(McpRedisConstants.TOOL_STATES_TTL_SECONDS));
            log.info("Rebuilt Hash key {} with {} tools", hashKey, tools.size());
        } catch (JsonProcessingException e) {
            log.error("Failed to serialize state snapshot for {}: {}", hashKey, e.getMessage());
        } catch (Exception e) {
            log.error("Failed to rebuild Hash key {}: {}", hashKey, e.getMessage());
        }
    }
}
