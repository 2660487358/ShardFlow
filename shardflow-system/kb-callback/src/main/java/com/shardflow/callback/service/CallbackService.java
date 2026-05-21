package com.shardflow.callback.service;

import com.shardflow.callback.util.IdempotencyUtil;
import com.shardflow.common.dto.ShardSaveRequest;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.data.redis.core.RedisTemplate;
import org.springframework.stereotype.Service;

import java.util.Map;
import java.util.UUID;

@Service
public class CallbackService {
    private static final Logger log = LoggerFactory.getLogger(CallbackService.class);
    private final RedisTemplate<String, Object> redisTemplate;
    private final IdempotencyUtil idempotencyUtil;

    public CallbackService(RedisTemplate<String, Object> redisTemplate, IdempotencyUtil idempotencyUtil) {
        this.redisTemplate = redisTemplate;
        this.idempotencyUtil = idempotencyUtil;
    }

    public Map<String, Object> saveShard(ShardSaveRequest request) {
        String shardId = UUID.randomUUID().toString();
        String key = "kb:" + request.tenantId() + ":shard:" + request.taskId() + ":latest";
        redisTemplate.opsForValue().set(key, shardId);
        log.info("Shard saved: taskId={}, shardId={}", request.taskId(), shardId);
        return Map.of("status", "ok", "shard_id", shardId, "task_id", request.taskId());
    }

    public Map<String, Object> saveStrategy(Map<String, Object> body) {
        log.info("Strategy saved: {}", body.get("strategy_id"));
        return Map.of("status", "ok");
    }

    public Map<String, Object> sessionComplete(Map<String, Object> body) {
        log.info("Session completed: {}", body.get("session_id"));
        return Map.of("status", "ok");
    }

    public Map<String, Object> writeAudit(Map<String, Object> body) {
        log.info("Audit: {}", body.get("event"));
        return Map.of("status", "ok");
    }

    public Map<String, Object> reportProgress(Map<String, Object> body) {
        redisTemplate.opsForValue().set(
            "kb:" + body.get("tenant_id") + ":progress:" + body.get("task_id"),
            String.valueOf(body.get("progress"))
        );
        return Map.of("status", "ok");
    }
}
