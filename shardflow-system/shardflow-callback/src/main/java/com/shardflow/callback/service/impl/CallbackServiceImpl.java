package com.shardflow.callback.service.impl;

import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import tools.jackson.core.JacksonException;
import tools.jackson.databind.ObjectMapper;
import com.shardflow.memory.repository.AuditLogRepository;
import com.shardflow.shard.service.SessionStateSummaryService;
import com.shardflow.profile.service.UserProfileService;
import com.shardflow.memory.service.MemoryChunkService;
import com.shardflow.common.dto.session.SessionSummaryCreateRequest;
import com.shardflow.common.dto.session.SessionSummaryCreateResponse;
import com.shardflow.common.dto.profile.UserProfileUpdateRequest;
import com.shardflow.common.dto.profile.UserProfileUpdateResponse;
import com.shardflow.common.dto.memory.MemoryCreateResponse;
import com.shardflow.common.dto.strategy.StrategyCreateResponse;
import com.shardflow.strategy.service.StrategyRecordService;
import com.shardflow.kb.service.KbShardService;
import com.shardflow.task.repository.TaskRepository;
import com.shardflow.callback.service.CallbackService;
import com.shardflow.common.entity.*;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.data.redis.core.RedisTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.time.Duration;
import java.util.List;
import java.util.Map;

@Slf4j
@Service
@RequiredArgsConstructor
public class CallbackServiceImpl implements CallbackService {

    private final RedisTemplate<String, Object> redisTemplate;
    private final ObjectMapper objectMapper;
    private final TaskRepository taskRepository;
    private final AuditLogRepository auditLogRepository;
    private final SessionStateSummaryService summaryService;
    private final UserProfileService profileService;
    private final MemoryChunkService memoryService;
    private final StrategyRecordService strategyService;
    private final KbShardService kbShardService;

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

        // S4.9 新增字段填充
        audit.setTraceId((String) body.get("trace_id"));
        audit.setSessionId((String) body.get("session_id"));
        audit.setOperationType((String) body.get("operation_type"));
        audit.setResourceType((String) body.get("resource_type"));
        audit.setResourceId((String) body.get("resource_id"));
        audit.setIpAddress((String) body.get("ip_address"));

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

    /**
     * POST /api/v1/callback/shards — Save session state summary from Python推理层.
     * Delegates to SessionStateSummaryService for persistence + Redis sync.
     */
    @Override
    @Transactional
    @SuppressWarnings("unchecked")
    public Map<String, Object> saveShard(Map<String, Object> body) {
        SessionSummaryCreateRequest request = new SessionSummaryCreateRequest();
        request.setUserId((String) body.get("user_id"));
        request.setTaskId((String) body.get("task_id"));
        request.setTaskType((String) body.get("task_type"));
        request.setTaskGoal((String) body.get("task_goal"));

        Object seqObj = body.get("session_seq");
        if (seqObj instanceof Number) {
            request.setSessionSeq(((Number) seqObj).intValue());
        }

        // Map knowledge_state
        Object ksObj = body.get("knowledge_state");
        if (ksObj instanceof Map) {
            Map<String, Object> ksMap = (Map<String, Object>) ksObj;
            SessionSummaryCreateRequest.KnowledgeState ks = new SessionSummaryCreateRequest.KnowledgeState();
            ks.setConfirmed((List<String>) ksMap.getOrDefault("confirmed", List.of()));
            ks.setExcluded((List<String>) ksMap.getOrDefault("excluded", List.of()));
            ks.setPending((List<String>) ksMap.getOrDefault("pending", List.of()));
            request.setKnowledgeState(ks);
        }

        // Map user_context
        Object ucObj = body.get("user_context");
        if (ucObj instanceof Map) {
            Map<String, Object> ucMap = (Map<String, Object>) ucObj;
            SessionSummaryCreateRequest.UserContext uc = new SessionSummaryCreateRequest.UserContext();
            uc.setExpertiseLevel((String) ucMap.getOrDefault("expertise_level", ""));
            uc.setPreferredDepth((String) ucMap.getOrDefault("preferred_depth", ""));
            uc.setCommunicationStyle((String) ucMap.getOrDefault("communication_style", ""));
            request.setUserContext(uc);
        }

        // Map execution_state
        Object esObj = body.get("execution_state");
        if (esObj instanceof Map) {
            Map<String, Object> esMap = (Map<String, Object>) esObj;
            SessionSummaryCreateRequest.ExecutionState es = new SessionSummaryCreateRequest.ExecutionState();
            Object stepsObj = esMap.get("completed_steps");
            if (stepsObj instanceof Number) es.setCompletedSteps(((Number) stepsObj).intValue());
            es.setCurrentStep((String) esMap.getOrDefault("current_step", ""));
            es.setToolsUsed((List<String>) esMap.getOrDefault("tools_used", List.of()));
            es.setEstimatedRemaining((String) esMap.getOrDefault("estimated_remaining", ""));
            request.setExecutionState(es);
        }

        // Map source_preference
        Object spObj = body.get("source_preference");
        if (spObj instanceof Map) {
            Map<String, Double> sp = (Map<String, Double>) spObj;
            request.setSourcePreference(sp);
        }

        SessionSummaryCreateResponse response = summaryService.saveFromCallback(request);
        log.info("Shard saved via callback: summaryId={}, status={}", response.getSummaryId(), response.getStatus());

        return Map.of(
            "success", true,
            "summary_id", response.getSummaryId(),
            "status", response.getStatus()
        );
    }

    /**
     * POST /api/v1/callback/profile — Save user profile from Python推理层.
     * Delegates to UserProfileService for persistence + Redis sync.
     */
    @Override
    @Transactional
    @SuppressWarnings("unchecked")
    public Map<String, Object> saveProfile(Map<String, Object> body) {
        String userId = (String) body.get("user_id");
        if (userId == null || userId.isBlank()) {
            return Map.of("success", false, "error", "user_id is required");
        }

        UserProfileUpdateRequest request = new UserProfileUpdateRequest();

        // Map preference data
        Object prefObj = body.get("preference");
        if (prefObj instanceof Map) {
            Map<String, Object> prefMap = (Map<String, Object>) prefObj;
            UserProfileUpdateRequest.ProfileData pref = new UserProfileUpdateRequest.ProfileData();
            if (prefMap.get("interests") instanceof List) {
                pref.setInterests((List<String>) prefMap.get("interests"));
            }
            pref.setExpertise((String) prefMap.getOrDefault("expertise", ""));
            pref.setCommunicationStyle((String) prefMap.getOrDefault("communication_style", ""));
            if (prefMap.get("preferred_sources") instanceof Map) {
                pref.setPreferredSources((Map<String, Double>) prefMap.get("preferred_sources"));
            }
            pref.setTimezone((String) prefMap.getOrDefault("timezone", ""));
            request.setPreference(pref);
        }

        // Map interaction_habits data
        Object habitsObj = body.get("interaction_habits");
        if (habitsObj instanceof Map) {
            Map<String, Object> habitsMap = (Map<String, Object>) habitsObj;
            UserProfileUpdateRequest.InteractionHabitsData habits = new UserProfileUpdateRequest.InteractionHabitsData();
            if (habitsMap.get("common_tasks") instanceof List) {
                habits.setCommonTasks((List<String>) habitsMap.get("common_tasks"));
            }
            habits.setPreferredDepth((String) habitsMap.getOrDefault("preferred_depth", ""));
            habits.setFeedbackPatterns((String) habitsMap.getOrDefault("feedback_patterns", ""));
            request.setInteractionHabits(habits);
        }

        UserProfileUpdateResponse response = profileService.saveFromCallback(userId, request);
        log.info("Profile saved via callback: userId={}, status={}, version={}",
                userId, response.getStatus(), response.getProfileVersion());

        return Map.of(
            "success", true,
            "profile_id", response.getProfileId() != null ? response.getProfileId() : "",
            "status", response.getStatus(),
            "profile_version", response.getProfileVersion() != null ? response.getProfileVersion() : 1
        );
    }

    /**
     * POST /api/v1/callback/memory — Save memory chunk from Python推理层.
     * Delegates to MemoryChunkService for persistence + Redis sync.
     */
    @Override
    @Transactional
    public Map<String, Object> saveMemory(Map<String, Object> body) {
        MemoryCreateResponse response = memoryService.saveFromCallback(body);
        log.info("Memory saved via callback: memoryId={}, status={}, conflict={}",
                response.getMemoryId(), response.getStatus(), response.getConflictDetected());

        return Map.of(
            "success", true,
            "memory_id", response.getMemoryId(),
            "status", response.getStatus(),
            "conflict_detected", response.getConflictDetected() != null ? response.getConflictDetected() : false
        );
    }

    /**
     * POST /api/v1/callback/strategies — Save strategy record from Python推理层.
     * Delegates to StrategyRecordService for persistence.
     * Per P6.2.3: Callback interface for strategy persistence.
     */
    @Override
    @Transactional
    public Map<String, Object> saveStrategyRecord(Map<String, Object> body) {
        StrategyCreateResponse response = strategyService.saveFromCallback(body);
        log.info("Strategy saved via callback: recordId={}, status={}, score={}",
                response.getRecordId(), response.getStatus(), response.getSuccessScore());

        return Map.of(
            "success", true,
            "record_id", response.getRecordId() != null ? response.getRecordId() : "",
            "status", response.getStatus(),
            "success_score", response.getSuccessScore() != null ? response.getSuccessScore() : 0.0
        );
    }

    private String toJson(Object obj) {
        try {
            return objectMapper.writeValueAsString(obj);
        } catch (JacksonException e) {
            log.warn("Failed to serialize object to JSON", e);
            return "{}";
        }
    }

    // ===== S4.6 新增回调接口实现 =====

    /**
     * CB-08: 记忆删除回调。
     */
    @Override
    @Transactional
    public Map<String, Object> deleteMemory(String userId, String key) {
        boolean deleted = memoryService.deleteMemory(key);
        log.info("Memory deleted via callback: userId={}, key={}, success={}", userId, key, deleted);
        return Map.of("success", deleted, "key", key);
    }

    /**
     * CB-09: 会话摘要回调。
     * Python 生成摘要后回调 Java 异步归档 PG。
     *
     * 注意：session:{session_id}:summary 与 session:{session_id}:summary:version
     * 的写入主权端为 Python（Redis-Key 规范 §3.1），Java 端仅通过 SummaryArchiveScheduler
     * 扫描归档 PG L2，不在此处写入 Redis，避免覆盖 Python 写入的完整摘要 JSON。
     */
    @Override
    @Transactional
    @SuppressWarnings("unchecked")
    public Map<String, Object> saveSessionSummary(Map<String, Object> body) {
        String sessionId = (String) body.get("session_id");
        String userId = (String) body.get("user_id");
        Object versionObj = body.get("version");
        Integer version = (versionObj instanceof Number n) ? n.intValue() : null;

        log.info("Session summary callback received: sessionId={}, userId={}, version={}. "
                + "Redis L1 is owned by Python; archive to PG will be done by SummaryArchiveScheduler.",
                sessionId, userId, version);
        return Map.of("archived", true, "version", version != null ? version : 0);
    }

    /**
     * CB-11: 策略删除回调。
     */
    @Override
    @Transactional
    public Map<String, Object> deleteStrategy(String recordId) {
        boolean deleted = strategyService.deleteStrategy(recordId);
        log.info("Strategy deleted via callback: recordId={}, success={}", recordId, deleted);
        return Map.of("success", deleted, "record_id", recordId);
    }

    /**
     * CB-12: 策略保存回调（显式 save 路径）。
     */
    @Override
    @Transactional
    public Map<String, Object> saveStrategy(Map<String, Object> body) {
        // 与 saveStrategyRecord 功能一致，路径统一
        return saveStrategyRecord(body);
    }

    /**
     * KB Shard 状态包回调（C-4.5）。
     */
    @Override
    @Transactional
    public Map<String, Object> saveKbShard(Map<String, Object> body) {
        Map<String, Object> result = kbShardService.saveFromCallback(body);
        log.info("KB shard saved via callback: shardId={}, status={}",
                result.get("shard_id"), result.get("status"));
        return result;
    }
}
