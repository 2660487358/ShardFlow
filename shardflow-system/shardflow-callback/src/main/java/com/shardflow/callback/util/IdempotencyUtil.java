package com.shardflow.callback.util;

import org.springframework.data.redis.core.RedisTemplate;
import org.springframework.stereotype.Component;

import java.time.Duration;

@Component
public class IdempotencyUtil {
    private final RedisTemplate<String, Object> redisTemplate;
    private static final Duration TTL = Duration.ofHours(24);

    public IdempotencyUtil(RedisTemplate<String, Object> redisTemplate) {
        this.redisTemplate = redisTemplate;
    }

    public boolean isDuplicate(String idempotencyKey) {
        return Boolean.TRUE.equals(redisTemplate.hasKey("idempotent:" + idempotencyKey));
    }

    public void mark(String idempotencyKey) {
        redisTemplate.opsForValue().set("idempotent:" + idempotencyKey, "1", TTL);
    }
}
