package com.shardflow.mcp.health;

import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.shardflow.common.config.McpRedisConstants;
import com.shardflow.common.entity.McpToolEntity;
import com.shardflow.mcp.health.McpHealthChecker.HealthCheckResult;
import com.shardflow.mcp.publisher.ToolStatePublisher;
import com.shardflow.mcp.repository.McpToolRepository;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.data.redis.core.RedisTemplate;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;

import java.time.Duration;
import java.time.Instant;
import java.util.List;
import java.util.Map;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

/**
 * MCP 工具健康检查调度器.
 * 实现定期健康检查、不可用自动标记、自动恢复、检查结果写入 Hash (FR-HEALTH-001/003/004/006).
 *
 * <p>调度逻辑：
 * <ul>
 *   <li>每 10s 检查所有 ACTIVE 且配置了 health_check_url 的工具</li>
 *   <li>连续 3 次失败 → 自动标记 INACTIVE + 唤醒信号</li>
 *   <li>连续 3 次成功 → 自动恢复 ACTIVE + 唤醒信号</li>
 *   <li>检查结果写入 Redis Hash (health 字段) + 刷新 TTL</li>
 * </ul>
 */
@Slf4j
@Component
@RequiredArgsConstructor
public class McpHealthCheckScheduler {

    private final McpToolRepository repository;
    private final McpHealthChecker healthChecker;
    private final ToolStatePublisher toolStatePublisher;
    private final RedisTemplate<String, Object> redisTemplate;
    private final ObjectMapper objectMapper;

    /** 连续失败计数器: toolId → 连续失败次数 */
    private final ConcurrentHashMap<String, Integer> failureCounters = new ConcurrentHashMap<>();

    /** 连续成功计数器: toolId → 连续成功次数（仅 INACTIVE 工具追踪恢复） */
    private final ConcurrentHashMap<String, Integer> successCounters = new ConcurrentHashMap<>();

    /** 健康检查线程池 */
    private final ExecutorService healthCheckExecutor = Executors.newFixedThreadPool(
        Runtime.getRuntime().availableProcessors(),
        r -> {
            Thread t = new Thread(r, "health-check-worker");
            t.setDaemon(true);
            return t;
        }
    );

    /**
     * 定期健康检查调度器 (FR-HEALTH-001).
     * 每 10s 间隔，检查所有 ACTIVE 且配置了 health_check_url 的工具.
     */
    @Scheduled(fixedRate = McpRedisConstants.HEALTH_CHECK_INTERVAL_MS, initialDelay = 15000)
    public void scheduleHealthChecks() {
        // 查询所有需要健康检查的工具：ACTIVE 且有 health_check_url
        List<McpToolEntity> toolsToCheck = repository.selectList(
            new LambdaQueryWrapper<McpToolEntity>()
                .eq(McpToolEntity::getStatus, "ACTIVE")
                .isNotNull(McpToolEntity::getHealthCheckUrl)
                .ne(McpToolEntity::getHealthCheckUrl, "")
        );

        if (toolsToCheck.isEmpty()) {
            return;
        }

        // 同时检查 INACTIVE 工具（用于自动恢复检测）
        List<McpToolEntity> inactiveTools = repository.selectList(
            new LambdaQueryWrapper<McpToolEntity>()
                .eq(McpToolEntity::getStatus, "INACTIVE")
                .isNotNull(McpToolEntity::getHealthCheckUrl)
                .ne(McpToolEntity::getHealthCheckUrl, "")
        );

        // 并行检查 ACTIVE 工具
        List<CompletableFuture<Void>> activeFutures = toolsToCheck.stream()
            .map(tool -> CompletableFuture.runAsync(() -> {
                try {
                    performHealthCheck(tool);
                } catch (Exception e) {
                    log.error("Health check error for tool {}: {}", tool.getToolId(), e.getMessage());
                }
            }, healthCheckExecutor))
            .toList();

        // 并行检查 INACTIVE 工具（自动恢复检测）
        List<CompletableFuture<Void>> inactiveFutures = inactiveTools.stream()
            .map(tool -> CompletableFuture.runAsync(() -> {
                try {
                    performRecoveryCheck(tool);
                } catch (Exception e) {
                    log.error("Recovery check error for tool {}: {}", tool.getToolId(), e.getMessage());
                }
            }, healthCheckExecutor))
            .toList();

        // 等待所有检查完成
        CompletableFuture.allOf(
            CompletableFuture.allOf(activeFutures.toArray(new CompletableFuture[0])),
            CompletableFuture.allOf(inactiveFutures.toArray(new CompletableFuture[0]))
        ).join();
    }

    /**
     * 手动触发健康检查 (FR-HEALTH-002).
     *
     * @param tool 工具实体
     * @return 检查结果
     */
    public HealthCheckResult manualCheck(McpToolEntity tool) {
        HealthCheckResult result = healthChecker.check(
            tool.getHealthCheckUrl(),
            tool.getTimeoutSeconds() != null ? tool.getTimeoutSeconds() : 30
        );

        // 更新健康状态
        String newHealthStatus = result.isHealthy() ? "HEALTHY" : "UNHEALTHY";
        tool.setHealthStatus(newHealthStatus);
        tool.setLastHealthCheckAt(Instant.now());
        repository.updateById(tool);

        // 写入 Hash
        updateHealthInHash(tool, newHealthStatus);

        return result;
    }

    /**
     * 获取工具连续失败次数.
     */
    public int getConsecutiveFailures(String toolId) {
        return failureCounters.getOrDefault(toolId, 0);
    }

    /**
     * 获取工具连续成功次数.
     */
    public int getConsecutiveSuccesses(String toolId) {
        return successCounters.getOrDefault(toolId, 0);
    }

    /**
     * 对 ACTIVE 工具执行健康检查.
     */
    private void performHealthCheck(McpToolEntity tool) {
        HealthCheckResult result = healthChecker.check(
            tool.getHealthCheckUrl(),
            tool.getTimeoutSeconds() != null ? tool.getTimeoutSeconds() : 30
        );

        String toolId = tool.getToolId();

        if (result.isHealthy()) {
            // 健康检查通过
            failureCounters.remove(toolId);
            successCounters.remove(toolId);

            // 更新健康状态为 HEALTHY
            if (!"HEALTHY".equals(tool.getHealthStatus())) {
                tool.setHealthStatus("HEALTHY");
                tool.setLastHealthCheckAt(Instant.now());
                repository.updateById(tool);
                log.info("Tool {} health status changed to HEALTHY", toolId);
            } else {
                tool.setLastHealthCheckAt(Instant.now());
                repository.updateById(tool);
            }

            // 写入 Hash (FR-HEALTH-001: 检查结果写入 Hash)
            updateHealthInHash(tool, "HEALTHY");

        } else {
            // 健康检查失败
            int failures = failureCounters.merge(toolId, 1, Integer::sum);
            successCounters.remove(toolId);

            // 更新健康状态为 UNHEALTHY
            tool.setHealthStatus("UNHEALTHY");
            tool.setLastHealthCheckAt(Instant.now());
            repository.updateById(tool);

            // 写入 Hash
            updateHealthInHash(tool, "UNHEALTHY");

            // FR-HEALTH-003: 健康检查告警
            log.warn("[HEALTH-ALERT] Tool {} health check failed ({}/{}): {}",
                toolId, failures, McpRedisConstants.HEALTH_CHECK_FAILURE_THRESHOLD,
                result.getMessage());

            // FR-HEALTH-001: 连续 3 次失败 → 自动标记 INACTIVE
            if (failures >= McpRedisConstants.HEALTH_CHECK_FAILURE_THRESHOLD) {
                markToolInactive(tool, failures);
                failureCounters.remove(toolId);
            }
        }
    }

    /**
     * 对 INACTIVE 工具执行恢复检查 (FR-HEALTH-004).
     */
    private void performRecoveryCheck(McpToolEntity tool) {
        HealthCheckResult result = healthChecker.check(
            tool.getHealthCheckUrl(),
            tool.getTimeoutSeconds() != null ? tool.getTimeoutSeconds() : 30
        );

        String toolId = tool.getToolId();

        if (result.isHealthy()) {
            int successes = successCounters.merge(toolId, 1, Integer::sum);

            // 更新健康状态
            tool.setHealthStatus("HEALTHY");
            tool.setLastHealthCheckAt(Instant.now());
            repository.updateById(tool);

            // FR-HEALTH-004: 连续 3 次通过 → 自动恢复 ACTIVE
            if (successes >= McpRedisConstants.HEALTH_CHECK_SUCCESS_THRESHOLD) {
                markToolActive(tool);
                successCounters.remove(toolId);
                failureCounters.remove(toolId);
            }
        } else {
            // 仍然不健康，重置成功计数
            successCounters.remove(toolId);
            tool.setHealthStatus("UNHEALTHY");
            tool.setLastHealthCheckAt(Instant.now());
            repository.updateById(tool);
        }
    }

    /**
     * 连续失败达到阈值，自动标记工具为 INACTIVE (FR-HEALTH-001).
     */
    private void markToolInactive(McpToolEntity tool, int failures) {
        String toolId = tool.getToolId();
        log.warn("[HEALTH-ALERT] Tool {} marked INACTIVE after {} consecutive failures",
            toolId, failures);

        tool.setStatus("INACTIVE");
        tool.setHealthStatus("UNHEALTHY");
        tool.setUpdatedBy("system-health-check");
        repository.updateById(tool);

        // 从 Hash 中移除工具状态 + 发布唤醒信号
        toolStatePublisher.removeToolState(tool);

        // 失效缓存
        String userId = tool.getUserId();
        redisTemplate.delete(com.shardflow.common.config.McpRedisConstants.toolsListKey(userId));
        redisTemplate.delete(com.shardflow.common.config.McpRedisConstants.toolDetailKey(userId, toolId));
        redisTemplate.delete(com.shardflow.common.config.McpRedisConstants.toolsDiscoverKey(userId));
    }

    /**
     * 连续成功达到阈值，自动恢复工具为 ACTIVE (FR-HEALTH-004).
     */
    private void markToolActive(McpToolEntity tool) {
        String toolId = tool.getToolId();
        log.info("[HEALTH-RECOVERY] Tool {} recovered to ACTIVE after {} consecutive successes",
            toolId, McpRedisConstants.HEALTH_CHECK_SUCCESS_THRESHOLD);

        tool.setStatus("ACTIVE");
        tool.setHealthStatus("HEALTHY");
        tool.setUpdatedBy("system-health-check");
        repository.updateById(tool);

        // 写入 Hash + 发布唤醒信号
        toolStatePublisher.publishStateChange(tool);

        // 失效缓存
        String userId = tool.getUserId();
        redisTemplate.delete(com.shardflow.common.config.McpRedisConstants.toolsListKey(userId));
        redisTemplate.delete(com.shardflow.common.config.McpRedisConstants.toolDetailKey(userId, toolId));
        redisTemplate.delete(com.shardflow.common.config.McpRedisConstants.toolsDiscoverKey(userId));
    }

    /**
     * 将健康检查结果写入 Redis Hash (FR-HEALTH-001).
     * 更新 Hash 中对应工具的 health 字段 + 刷新 TTL.
     */
    private void updateHealthInHash(McpToolEntity tool, String healthStatus) {
        String userId = tool.getUserId();
        String hashKey = McpRedisConstants.toolStatesKey(userId);

        try {
            // 读取当前 Hash 中的工具状态
            Object existing = redisTemplate.opsForHash().get(hashKey, tool.getToolId());
            Map<String, Object> stateSnapshot;

            if (existing != null) {
                @SuppressWarnings("unchecked")
                Map<String, Object> existingMap = objectMapper.readValue(
                    existing.toString(), Map.class);
                stateSnapshot = new java.util.HashMap<>(existingMap);
            } else {
                stateSnapshot = new java.util.LinkedHashMap<>();
            }

            // 更新 health 和 updated_at
            stateSnapshot.put("health", healthStatus);
            stateSnapshot.put("status", tool.getStatus());
            stateSnapshot.put("version", tool.getVersion() != null ? tool.getVersion() : "1.0.0");
            stateSnapshot.put("updated_at", Instant.now().toString());

            String stateJson = objectMapper.writeValueAsString(stateSnapshot);

            // HSET 更新 Hash
            redisTemplate.opsForHash().put(hashKey, tool.getToolId(), stateJson);

            // EXPIRE 刷新 TTL
            redisTemplate.expire(hashKey, Duration.ofSeconds(McpRedisConstants.TOOL_STATES_TTL_SECONDS));

        } catch (JsonProcessingException e) {
            log.error("Failed to update health in Hash for tool {}: {}", tool.getToolId(), e.getMessage());
        }
    }
}
