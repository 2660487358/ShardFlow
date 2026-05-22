package com.shardflow.callback.service;

import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.shardflow.callback.repository.*;
import com.shardflow.common.dto.ShardSaveRequest;
import com.shardflow.common.entity.*;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.data.redis.core.RedisTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.time.Duration;
import java.time.Instant;
import java.util.Map;
import java.util.UUID;

@Service
public class CallbackService {
    private static final Logger log = LoggerFactory.getLogger(CallbackService.class);
    private final RedisTemplate<String, Object> redisTemplate;
    private final ObjectMapper objectMapper;
    private final ShardRepository shardRepository;
    private final StrategyRepository strategyRepository;
    private final TaskRepository taskRepository;
    private final AuditLogRepository auditLogRepository;

    public CallbackService(RedisTemplate<String, Object> redisTemplate,
                           ObjectMapper objectMapper,
                           ShardRepository shardRepository,
                           StrategyRepository strategyRepository,
                           TaskRepository taskRepository,
                           AuditLogRepository auditLogRepository) {
        this.redisTemplate = redisTemplate;
        this.objectMapper = objectMapper;
        this.shardRepository = shardRepository;
        this.strategyRepository = strategyRepository;
        this.taskRepository = taskRepository;
        this.auditLogRepository = auditLogRepository;
    }

    @Transactional
    public Map<String, Object> saveShard(ShardSaveRequest request) {
        ShardEntity shard = shardRepository
            .findByUserIdAndTaskId(request.userId(), request.taskId())
            .orElseGet(ShardEntity::new);

        shard.setUserId(request.userId());
        shard.setTaskId(request.taskId());
        shard.setSessionSeq(request.sessionSeq());
        if (request.confirmed() != null) shard.setConfirmed(toJson(request.confirmed()));
        if (request.excluded() != null) shard.setExcluded(toJson(request.excluded()));
        if (request.pending() != null) shard.setPending(toJson(request.pending()));
        if (request.sourcePreference() != null) shard.setSourcePreference(toJson(request.sourcePreference()));
        if (request.keyDecisions() != null) shard.setKeyDecisions(toJson(request.keyDecisions()));

        shardRepository.save(shard);

        String cacheKey = "shardflow:" + request.userId() + ":shard:" + request.taskId() + ":latest";
        redisTemplate.opsForValue().set(cacheKey, shard.getId(), Duration.ofHours(24));

        log.info("Shard persisted: userId={}, taskId={}, shardId={}", request.userId(), request.taskId(), shard.getId());
        return Map.of("success", true, "shard_id", shard.getId());
    }

    @Transactional
    public Map<String, Object> saveStrategy(Map<String, Object> body) {
        StrategyEntity strategy = new StrategyEntity();
        strategy.setStrategyId((String) body.getOrDefault("strategy_id", UUID.randomUUID().toString()));
        strategy.setUserId((String) body.get("user_id"));
        strategy.setTaskType((String) body.getOrDefault("task_type", "general"));
        strategy.setSourceCombo(toJson(body.get("source_combo")));
        strategyRepository.save(strategy);
        log.info("Strategy persisted: {}", strategy.getStrategyId());
        return Map.of("success", true, "strategy_id", strategy.getStrategyId());
    }

    @Transactional
    public Map<String, Object> sessionComplete(Map<String, Object> body) {
        String taskId = (String) body.get("task_id");
        taskRepository.findById(taskId).ifPresent(task -> {
            task.setStatus("COMPLETED");
            taskRepository.save(task);
        });
        log.info("Session completed: taskId={}", taskId);
        return Map.of("success", true);
    }

    @Transactional
    public Map<String, Object> writeAudit(Map<String, Object> body) {
        AuditLogEntity audit = new AuditLogEntity();
        audit.setUserId((String) body.get("user_id"));
        audit.setToolName((String) body.get("tool_name"));
        audit.setParamsSummary((String) body.get("params_summary"));
        audit.setSuccess(Boolean.TRUE.equals(body.get("success")));
        audit.setError((String) body.get("error"));
        Object latency = body.get("latency_ms");
        if (latency instanceof Number) audit.setLatencyMs(((Number) latency).longValue());
        auditLogRepository.save(audit);
        return Map.of("success", true);
    }

    @Transactional
    public Map<String, Object> reportProgress(Map<String, Object> body) {
        String progressKey = "shardflow:" + body.get("user_id") + ":progress:" + body.get("task_id");
        redisTemplate.opsForValue().set(progressKey, String.valueOf(body.get("progress")), Duration.ofHours(1));
        return Map.of("success", true);
    }

    private String toJson(Object obj) {
        try {
            return objectMapper.writeValueAsString(obj);
        } catch (JsonProcessingException e) {
            log.warn("Failed to serialize object to JSON", e);
            return "{}";
        }
    }
}
