package com.shardflow.callback.service.impl;

import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.shardflow.callback.repository.AuditLogRepository;
import com.shardflow.shard.repository.ShardRepository;
import com.shardflow.strategy.repository.StrategyRepository;
import com.shardflow.task.repository.TaskRepository;
import com.shardflow.callback.service.CallbackService;
import com.shardflow.common.dto.ShardSaveRequest;
import com.shardflow.common.entity.*;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.data.redis.core.RedisTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.time.Duration;
import java.util.Map;
import java.util.UUID;

@Slf4j
@Service
@RequiredArgsConstructor
public class CallbackServiceImpl implements CallbackService {

    private final RedisTemplate<String, Object> redisTemplate;
    private final ObjectMapper objectMapper;
    private final ShardRepository shardRepository;
    private final StrategyRepository strategyRepository;
    private final TaskRepository taskRepository;
    private final AuditLogRepository auditLogRepository;

    @Override
    @Transactional
    public Map<String, Object> saveShard(ShardSaveRequest request) {
        ShardEntity shard = shardRepository.selectOne(
            new LambdaQueryWrapper<ShardEntity>()
                .eq(ShardEntity::getUserId, request.userId())
                .eq(ShardEntity::getTaskId, request.taskId())
        );
        if (shard == null) shard = new ShardEntity();

        shard.setUserId(request.userId());
        shard.setTaskId(request.taskId());
        shard.setSessionSeq(request.sessionSeq());
        if (request.confirmed() != null) shard.setConfirmed(toJson(request.confirmed()));
        if (request.excluded() != null) shard.setExcluded(toJson(request.excluded()));
        if (request.pending() != null) shard.setPending(toJson(request.pending()));
        if (request.sourcePreference() != null) shard.setSourcePreference(toJson(request.sourcePreference()));
        if (request.keyDecisions() != null) shard.setKeyDecisions(toJson(request.keyDecisions()));

        shardRepository.insertOrUpdate(shard);

        String cacheKey = "shardflow:" + request.userId() + ":shard:" + request.taskId() + ":latest";
        redisTemplate.opsForValue().set(cacheKey, String.valueOf(shard.getId()), Duration.ofHours(24));

        log.info("Shard persisted: userId={}, taskId={}, shardId={}", request.userId(), request.taskId(), shard.getId());
        return Map.of("success", true, "shard_id", shard.getId());
    }

    @Override
    @Transactional
    public Map<String, Object> saveStrategy(Map<String, Object> body) {
        StrategyEntity strategy = new StrategyEntity();
        strategy.setStrategyCode((String) body.getOrDefault("strategy_id", UUID.randomUUID().toString()));
        strategy.setUserId((String) body.get("user_id"));
        strategy.setTaskType((String) body.getOrDefault("task_type", "general"));
        strategy.setSourceCombo(toJson(body.get("source_combo")));
        strategyRepository.insert(strategy);

        log.info("Strategy persisted: {}", strategy.getStrategyCode());
        return Map.of("success", true, "strategy_id", strategy.getStrategyCode());
    }

    @Override
    @Transactional
    public Map<String, Object> sessionComplete(Map<String, Object> body) {
        String taskCode = (String) body.get("task_id");
        TaskEntity task = taskRepository.selectOne(
            new LambdaQueryWrapper<TaskEntity>().eq(TaskEntity::getTaskCode, taskCode));
        if (task != null) {
            task.setStatus("COMPLETED");
            taskRepository.updateById(task);
        }
        log.info("Session completed: taskCode={}", taskCode);
        return Map.of("success", true);
    }

    @Override
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
        auditLogRepository.insert(audit);
        return Map.of("success", true);
    }

    @Override
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
