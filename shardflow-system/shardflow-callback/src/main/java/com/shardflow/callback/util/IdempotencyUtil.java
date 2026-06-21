package com.shardflow.callback.util;

import tools.jackson.core.type.TypeReference;
import tools.jackson.databind.ObjectMapper;
import lombok.extern.slf4j.Slf4j;
import org.springframework.data.redis.core.RedisTemplate;
import org.springframework.stereotype.Component;

import java.time.Duration;
import java.util.Map;
import java.util.Optional;

/**
 * 幂等工具（C-4.20 增强版）。
 * <p>
 * 规则条款：C-4.20（幂等键）、C-6.5（版本号乐观锁）、C-4.8（回调接口幂等）。
 * <p>
 * 增强点：
 * 1. 使用 Redis {@code SETNX}（setIfAbsent）原子操作，避免 check-then-mark 竞态条件。
 * 2. 缓存首次响应结果，重复请求直接返回缓存响应，保证调用方语义一致。
 * 3. 支持复合幂等键（user_id + request_id），符合 Redis Key 规范 {@code shardflow:idempotent:{request_id}}。
 * 4. 区分"首次执行"与"重复命中"两种状态，便于上层日志与监控。
 */
@Slf4j
@Component
public class IdempotencyUtil {

    private final RedisTemplate<String, Object> redisTemplate;
    private final ObjectMapper objectMapper;

    /** 幂等键默认 TTL：300 秒（C-4.20） */
    private static final Duration DEFAULT_TTL = Duration.ofSeconds(300);

    /** 幂等键前缀，符合 Redis Key 规范 3.10 节 */
    private static final String KEY_PREFIX = "shardflow:idempotent:";

    /** 标记位：表示请求已被占用但响应尚未写入 */
    private static final String MARKER_PROCESSING = "__PROCESSING__";

    public IdempotencyUtil(RedisTemplate<String, Object> redisTemplate, ObjectMapper objectMapper) {
        this.redisTemplate = redisTemplate;
        this.objectMapper = objectMapper;
    }

    /**
     * 原子抢占幂等键（SETNX）。
     * <p>
     * 返回 true 表示当前请求获得执行权（首次），返回 false 表示重复请求已被处理或正在处理。
     *
     * @param idempotencyKey 幂等键（通常为 X-Request-ID 或 user_id + request_id 复合键）
     * @return true=首次获得执行权，false=重复请求
     */
    public boolean tryAcquire(String idempotencyKey) {
        String key = KEY_PREFIX + idempotencyKey;
        Boolean acquired = redisTemplate.opsForValue()
                .setIfAbsent(key, MARKER_PROCESSING, DEFAULT_TTL);
        boolean ok = Boolean.TRUE.equals(acquired);
        if (!ok) {
            log.debug("Idempotency hit (duplicate request): key={}", key);
        }
        return ok;
    }

    /**
     * 写入首次响应结果，供后续重复请求复用。
     */
    public void storeResponse(String idempotencyKey, Map<String, Object> response) {
        String key = KEY_PREFIX + idempotencyKey;
        try {
            String json = objectMapper.writeValueAsString(response);
            redisTemplate.opsForValue().set(key, json, DEFAULT_TTL);
        } catch (Exception e) {
            log.warn("Failed to store idempotent response for key={}: {}", key, e.getMessage());
        }
    }

    /**
     * 读取已缓存的响应结果（重复请求复用）。
     */
    @SuppressWarnings("unchecked")
    public Optional<Map<String, Object>> getCachedResponse(String idempotencyKey) {
        String key = KEY_PREFIX + idempotencyKey;
        Object cached = redisTemplate.opsForValue().get(key);
        if (cached == null || MARKER_PROCESSING.equals(cached)) {
            return Optional.empty();
        }
        try {
            if (cached instanceof String str) {
                return Optional.of(objectMapper.readValue(str, new TypeReference<Map<String, Object>>() {}));
            }
            if (cached instanceof Map<?, ?> map) {
                return Optional.of((Map<String, Object>) map);
            }
        } catch (Exception e) {
            log.warn("Failed to deserialize cached response for key={}: {}", key, e.getMessage());
        }
        return Optional.empty();
    }

    /**
     * 释放幂等键（执行失败时回滚，允许重试）。
     */
    public void release(String idempotencyKey) {
        String key = KEY_PREFIX + idempotencyKey;
        redisTemplate.delete(key);
    }

    /**
     * 判断是否为重复请求（不抢占）。
     */
    public boolean isDuplicate(String idempotencyKey) {
        return Boolean.TRUE.equals(redisTemplate.hasKey(KEY_PREFIX + idempotencyKey));
    }

    /**
     * 旧版 mark 方法（保留向后兼容，内部委托 tryAcquire）。
     *
     * @deprecated 使用 {@link #tryAcquire(String)} 替代，避免竞态条件。
     */
    @Deprecated
    public void mark(String idempotencyKey) {
        redisTemplate.opsForValue().set(KEY_PREFIX + idempotencyKey, MARKER_PROCESSING, DEFAULT_TTL);
    }

    /**
     * 构造复合幂等键：user_id + request_id，避免跨用户请求 ID 碰撞。
     */
    public static String buildKey(String userId, String requestId) {
        if (userId == null && requestId == null) return null;
        if (userId == null || userId.isBlank()) return requestId;
        if (requestId == null || requestId.isBlank()) return null;
        return userId + ":" + requestId;
    }
}
