package com.shardflow.config.support;

import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Component;
import org.springframework.web.server.ResponseStatusException;

import java.time.Duration;
import java.time.Instant;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ConcurrentMap;
import java.util.concurrent.atomic.AtomicInteger;

/**
 * Skill 级熔断器.
 *
 * <p>Per Skills管理需求规格文档 FR-8.5 / 实施计划 P6.3.
 *
 * <p>三状态机：
 * <ul>
 *   <li>CLOSED：正常放行，连续失败 5 次后切换到 OPEN</li>
 *   <li>OPEN：拒绝所有请求，60 秒后切换到 HALF_OPEN</li>
 *   <li>HALF_OPEN：允许最多 3 次试探请求，全部成功则切换回 CLOSED，
 *       任一失败则切换回 OPEN</li>
 * </ul>
 *
 * <p>状态存储：内存（ConcurrentHashMap）+ Redis（可选，多实例同步）.
 * <p>触发熔断时记录告警日志（P6.3.3）.
 */
@Slf4j
@Component
@RequiredArgsConstructor
public class SkillCircuitBreaker {

    /** 失败阈值：连续失败 5 次触发熔断 */
    public static final int FAILURE_THRESHOLD = 5;
    /** 恢复时间：OPEN 状态 60 秒后尝试恢复 */
    public static final Duration RECOVERY_DURATION = Duration.ofSeconds(60);
    /** 半开状态最大试探次数 */
    public static final int HALF_OPEN_MAX_TRIALS = 3;

    private static final String STATE_CLOSED = "CLOSED";
    private static final String STATE_OPEN = "OPEN";
    private static final String STATE_HALF_OPEN = "HALF_OPEN";

    /** Redis Key 前缀：shardflow:skill:breaker:{skillCode} */
    private static final String REDIS_KEY_PREFIX = "shardflow:skill:breaker:";

    private final StringRedisTemplate redisTemplate;

    /** 内存状态存储：skillCode -> BreakerState */
    private final ConcurrentMap<String, BreakerState> memoryStates = new ConcurrentHashMap<>();

    /**
     * 检查是否允许调用 Skill（熔断器闸门）.
     *
     * <p>FR-8.5: OPEN 状态拒绝所有请求.
     *
     * @param skillCode Skill 编码
     * @throws ResponseStatusException 当熔断器处于 OPEN 状态时抛出 503
     */
    public void checkAllowed(String skillCode) {
        BreakerState state = getOrCreateState(skillCode);
        synchronized (state) {
            String current = state.status;
            if (STATE_OPEN.equals(current)) {
                // 检查是否已过恢复时间
                if (Instant.now().isAfter(state.openedAt.plus(RECOVERY_DURATION))) {
                    // 切换到 HALF_OPEN
                    state.status = STATE_HALF_OPEN;
                    state.halfOpenTrials.set(0);
                    state.lastTransitionAt = Instant.now();
                    log.info("SkillCircuitBreaker: {} OPEN -> HALF_OPEN", skillCode);
                    persistState(skillCode, state);
                } else {
                    // 仍在 OPEN 状态，拒绝请求
                    throw new ResponseStatusException(HttpStatus.SERVICE_UNAVAILABLE,
                            "SKILL_CIRCUIT_OPEN: Skill " + skillCode
                                    + " is in circuit breaker OPEN state");
                }
            }

            if (STATE_HALF_OPEN.equals(state.status)) {
                // 半开状态最多允许 3 次试探
                if (state.halfOpenTrials.incrementAndGet() > HALF_OPEN_MAX_TRIALS) {
                    throw new ResponseStatusException(HttpStatus.SERVICE_UNAVAILABLE,
                            "SKILL_CIRCUIT_HALF_OPEN: Skill " + skillCode
                                    + " is in circuit breaker HALF_OPEN state, max trials exceeded");
                }
            }
        }
    }

    /**
     * 记录调用成功.
     *
     * <p>HALF_OPEN 状态下成功调用达到阈值时切换回 CLOSED.
     *
     * @param skillCode Skill 编码
     */
    public void recordSuccess(String skillCode) {
        BreakerState state = getOrCreateState(skillCode);
        synchronized (state) {
            if (STATE_HALF_OPEN.equals(state.status)) {
                // 半开状态下成功，重置为 CLOSED
                state.status = STATE_CLOSED;
                state.consecutiveFailures.set(0);
                state.halfOpenTrials.set(0);
                state.lastTransitionAt = Instant.now();
                log.info("SkillCircuitBreaker: {} HALF_OPEN -> CLOSED (recovered)", skillCode);
                persistState(skillCode, state);
            } else if (STATE_CLOSED.equals(state.status)) {
                // 关闭状态下成功，重置失败计数
                state.consecutiveFailures.set(0);
            }
        }
    }

    /**
     * 记录调用失败.
     *
     * <p>FR-8.5: 连续失败 5 次触发熔断.
     *
     * @param skillCode Skill 编码
     * @param error     错误信息
     */
    public void recordFailure(String skillCode, String error) {
        BreakerState state = getOrCreateState(skillCode);
        synchronized (state) {
            if (STATE_HALF_OPEN.equals(state.status)) {
                // 半开状态下失败，重新切换到 OPEN
                state.status = STATE_OPEN;
                state.openedAt = Instant.now();
                state.lastTransitionAt = Instant.now();
                log.warn("SkillCircuitBreaker: {} HALF_OPEN -> OPEN (trial failed): {}",
                        skillCode, error);
                alertCircuitOpen(skillCode, error);
                persistState(skillCode, state);
                return;
            }

            if (STATE_CLOSED.equals(state.status)) {
                int failures = state.consecutiveFailures.incrementAndGet();
                if (failures >= FAILURE_THRESHOLD) {
                    // 连续失败达到阈值，切换到 OPEN
                    state.status = STATE_OPEN;
                    state.openedAt = Instant.now();
                    state.lastTransitionAt = Instant.now();
                    log.warn("SkillCircuitBreaker: {} CLOSED -> OPEN (failures={})",
                            skillCode, failures);
                    alertCircuitOpen(skillCode, "Consecutive failures: " + failures);
                    persistState(skillCode, state);
                }
            }
        }
    }

    /**
     * 查询熔断器当前状态.
     *
     * @param skillCode Skill 编码
     * @return 状态信息（status, failures, openedAt）
     */
    public BreakerStatus getStatus(String skillCode) {
        BreakerState state = getOrCreateState(skillCode);
        synchronized (state) {
            return new BreakerStatus(
                    skillCode,
                    state.status,
                    state.consecutiveFailures.get(),
                    state.halfOpenTrials.get(),
                    state.openedAt,
                    state.lastTransitionAt
            );
        }
    }

    /**
     * 手动重置熔断器（管理员操作）.
     *
     * @param skillCode Skill 编码
     */
    public void reset(String skillCode) {
        BreakerState state = getOrCreateState(skillCode);
        synchronized (state) {
            state.status = STATE_CLOSED;
            state.consecutiveFailures.set(0);
            state.halfOpenTrials.set(0);
            state.openedAt = null;
            state.lastTransitionAt = Instant.now();
            log.info("SkillCircuitBreaker: {} manually reset to CLOSED", skillCode);
            persistState(skillCode, state);
        }
    }

    // ── 内部方法 ──

    private BreakerState getOrCreateState(String skillCode) {
        return memoryStates.computeIfAbsent(skillCode, k -> {
            // 尝试从 Redis 加载状态
            BreakerState loaded = loadStateFromRedis(k);
            return loaded != null ? loaded : new BreakerState();
        });
    }

    private BreakerState loadStateFromRedis(String skillCode) {
        try {
            String key = REDIS_KEY_PREFIX + skillCode;
            String status = redisTemplate.opsForValue().get(key + ":status");
            if (status == null) {
                return null;
            }
            BreakerState state = new BreakerState();
            state.status = status;
            String failuresStr = redisTemplate.opsForValue().get(key + ":failures");
            if (failuresStr != null) {
                state.consecutiveFailures.set(Integer.parseInt(failuresStr));
            }
            String openedAtStr = redisTemplate.opsForValue().get(key + ":opened_at");
            if (openedAtStr != null) {
                state.openedAt = Instant.parse(openedAtStr);
            }
            return state;
        } catch (Exception e) {
            log.warn("SkillCircuitBreaker: failed to load state from Redis skill={} error={}",
                    skillCode, e.getMessage());
            return null;
        }
    }

    private void persistState(String skillCode, BreakerState state) {
        try {
            String key = REDIS_KEY_PREFIX + skillCode;
            // 状态持久化 5 分钟（与 Skill 缓存 TTL 对齐）
            Duration ttl = Duration.ofMinutes(5);
            redisTemplate.opsForValue().set(key + ":status", state.status, ttl);
            redisTemplate.opsForValue().set(key + ":failures",
                    String.valueOf(state.consecutiveFailures.get()), ttl);
            if (state.openedAt != null) {
                redisTemplate.opsForValue().set(key + ":opened_at",
                        state.openedAt.toString(), ttl);
            }
        } catch (Exception e) {
            log.warn("SkillCircuitBreaker: failed to persist state to Redis skill={} error={}",
                    skillCode, e.getMessage());
        }
    }

    /**
     * 触发熔断告警（P6.3.3）.
     * V1 简化：仅记录 WARN 日志，V2 阶段对接告警系统（AlertManager/Prometheus）.
     */
    private void alertCircuitOpen(String skillCode, String reason) {
        log.warn("SKILL_CIRCUIT_BREAKER_ALERT: skill={} reason={} timestamp={}",
                skillCode, reason, Instant.now());
        // V2 阶段：通过 Webhook/邮件/Slack 发送告警
    }

    // ── 内部状态类 ──

    private static class BreakerState {
        String status = STATE_CLOSED;
        final AtomicInteger consecutiveFailures = new AtomicInteger(0);
        final AtomicInteger halfOpenTrials = new AtomicInteger(0);
        Instant openedAt = null;
        Instant lastTransitionAt = Instant.now();
    }

    /**
     * 熔断器状态快照（对外查询用）.
     */
    public record BreakerStatus(
            String skillCode,
            String status,
            int consecutiveFailures,
            int halfOpenTrials,
            Instant openedAt,
            Instant lastTransitionAt
    ) {}
}
