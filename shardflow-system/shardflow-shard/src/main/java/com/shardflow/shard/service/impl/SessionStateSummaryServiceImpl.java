package com.shardflow.shard.service.impl;

import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import com.baomidou.mybatisplus.core.conditions.update.LambdaUpdateWrapper;
import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.shardflow.common.dto.session.SessionSummaryCreateRequest;
import com.shardflow.common.dto.session.SessionSummaryCreateResponse;
import com.shardflow.common.entity.SessionStateSummaryEntity;
import com.shardflow.shard.repository.SessionStateSummaryRepository;
import com.shardflow.shard.service.SessionStateSummaryService;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.data.redis.core.RedisTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.time.Duration;
import java.time.Instant;
import java.util.List;
import java.util.Optional;
import java.util.UUID;

@Slf4j
@Service
@RequiredArgsConstructor
public class SessionStateSummaryServiceImpl implements SessionStateSummaryService {

    private final SessionStateSummaryRepository repository;
    private final RedisTemplate<String, Object> redisTemplate;
    private final ObjectMapper objectMapper;

    /** Redis key pattern for summary cache: shardflow:{userId}:sss:{taskId}:latest */
    private static final String REDIS_KEY_PATTERN = "shardflow:%s:sss:%s:latest";
    private static final Duration REDIS_TTL = Duration.ofHours(24);

    @Override
    @Transactional
    public SessionSummaryCreateResponse createSummary(SessionSummaryCreateRequest request) {
        SessionStateSummaryEntity entity = toEntity(request);
        entity.setSummaryId(generateSummaryId());
        entity.setVersion(1);
        entity.setIsDeleted(false);
        repository.insert(entity);

        // Sync to Redis cache
        syncToRedis(entity);

        log.info("Created session state summary: summaryId={}, userId={}, taskId={}",
                entity.getSummaryId(), entity.getUserId(), entity.getTaskId());

        return new SessionSummaryCreateResponse(
                entity.getSummaryId(), "created", entity.getCreatedAt());
    }

    @Override
    public Optional<SessionStateSummaryEntity> getSummary(String summaryId) {
        SessionStateSummaryEntity entity = repository.selectOne(
                new LambdaQueryWrapper<SessionStateSummaryEntity>()
                        .eq(SessionStateSummaryEntity::getSummaryId, summaryId)
                        .eq(SessionStateSummaryEntity::getIsDeleted, false));
        return Optional.ofNullable(entity);
    }

    @Override
    public Optional<SessionStateSummaryEntity> getLatestByUserAndTask(String userId, String taskId) {
        // Try Redis cache first
        SessionStateSummaryEntity cached = loadFromRedis(userId, taskId);
        if (cached != null) {
            return Optional.of(cached);
        }

        // Fall back to MySQL
        SessionStateSummaryEntity entity = repository.selectOne(
                new LambdaQueryWrapper<SessionStateSummaryEntity>()
                        .eq(SessionStateSummaryEntity::getUserId, userId)
                        .eq(SessionStateSummaryEntity::getTaskId, taskId)
                        .eq(SessionStateSummaryEntity::getIsDeleted, false)
                        .orderByDesc(SessionStateSummaryEntity::getVersion)
                        .last("LIMIT 1"));

        if (entity != null) {
            syncToRedis(entity);
        }
        return Optional.ofNullable(entity);
    }

    @Override
    public List<SessionStateSummaryEntity> listByUser(String userId) {
        return repository.selectList(
                new LambdaQueryWrapper<SessionStateSummaryEntity>()
                        .eq(SessionStateSummaryEntity::getUserId, userId)
                        .eq(SessionStateSummaryEntity::getIsDeleted, false)
                        .orderByDesc(SessionStateSummaryEntity::getCreatedAt));
    }

    @Override
    public List<SessionStateSummaryEntity> listByUserAndTask(String userId, String taskId) {
        return repository.selectList(
                new LambdaQueryWrapper<SessionStateSummaryEntity>()
                        .eq(SessionStateSummaryEntity::getUserId, userId)
                        .eq(SessionStateSummaryEntity::getTaskId, taskId)
                        .eq(SessionStateSummaryEntity::getIsDeleted, false)
                        .orderByDesc(SessionStateSummaryEntity::getVersion));
    }

    @Override
    @Transactional
    public Optional<SessionStateSummaryEntity> updateSummary(String summaryId, SessionSummaryCreateRequest request) {
        SessionStateSummaryEntity existing = repository.selectOne(
                new LambdaQueryWrapper<SessionStateSummaryEntity>()
                        .eq(SessionStateSummaryEntity::getSummaryId, summaryId)
                        .eq(SessionStateSummaryEntity::getIsDeleted, false));

        if (existing == null) {
            return Optional.empty();
        }

        // Update fields
        updateEntityFromRequest(existing, request);
        existing.setVersion(existing.getVersion() + 1);
        repository.updateById(existing);

        // Sync to Redis cache
        syncToRedis(existing);

        log.info("Updated session state summary: summaryId={}, version={}",
                summaryId, existing.getVersion());

        return Optional.of(existing);
    }

    @Override
    @Transactional
    public boolean deleteSummary(String summaryId) {
        int updated = repository.update(null,
                new LambdaUpdateWrapper<SessionStateSummaryEntity>()
                        .eq(SessionStateSummaryEntity::getSummaryId, summaryId)
                        .set(SessionStateSummaryEntity::getIsDeleted, true));

        // Also remove from Redis cache
        SessionStateSummaryEntity entity = repository.selectOne(
                new LambdaQueryWrapper<SessionStateSummaryEntity>()
                        .eq(SessionStateSummaryEntity::getSummaryId, summaryId));
        if (entity != null) {
            removeFromRedis(entity.getUserId(), entity.getTaskId());
        }

        return updated > 0;
    }

    @Override
    @Transactional
    public SessionSummaryCreateResponse saveFromCallback(SessionSummaryCreateRequest request) {
        // Check if a summary already exists for this user+task
        SessionStateSummaryEntity existing = repository.selectOne(
                new LambdaQueryWrapper<SessionStateSummaryEntity>()
                        .eq(SessionStateSummaryEntity::getUserId, request.getUserId())
                        .eq(SessionStateSummaryEntity::getTaskId, request.getTaskId())
                        .eq(SessionStateSummaryEntity::getIsDeleted, false)
                        .orderByDesc(SessionStateSummaryEntity::getVersion)
                        .last("LIMIT 1"));

        if (existing != null) {
            // Update existing: increment version
            updateEntityFromRequest(existing, request);
            existing.setVersion(existing.getVersion() + 1);
            repository.updateById(existing);
            syncToRedis(existing);

            log.info("Callback updated summary: summaryId={}, version={}",
                    existing.getSummaryId(), existing.getVersion());

            return new SessionSummaryCreateResponse(
                    existing.getSummaryId(), "updated", existing.getUpdatedAt());
        } else {
            // Create new
            return createSummary(request);
        }
    }

    // ------------------------------------------------------------------
    // Redis cache sync (P2.3.4)
    // ------------------------------------------------------------------

    private void syncToRedis(SessionStateSummaryEntity entity) {
        try {
            String key = String.format(REDIS_KEY_PATTERN, entity.getUserId(), entity.getTaskId());
            String json = objectMapper.writeValueAsString(entity);
            redisTemplate.opsForValue().set(key, json, REDIS_TTL);
            log.debug("Synced summary to Redis: key={}", key);
        } catch (JsonProcessingException e) {
            log.warn("Failed to sync summary to Redis: {}", e.getMessage());
        }
    }

    private SessionStateSummaryEntity loadFromRedis(String userId, String taskId) {
        try {
            String key = String.format(REDIS_KEY_PATTERN, userId, taskId);
            Object raw = redisTemplate.opsForValue().get(key);
            if (raw instanceof String json) {
                return objectMapper.readValue(json, SessionStateSummaryEntity.class);
            }
        } catch (Exception e) {
            log.debug("Redis cache miss for summary {}/{}: {}", userId, taskId, e.getMessage());
        }
        return null;
    }

    private void removeFromRedis(String userId, String taskId) {
        try {
            String key = String.format(REDIS_KEY_PATTERN, userId, taskId);
            redisTemplate.delete(key);
        } catch (Exception e) {
            log.warn("Failed to remove summary from Redis: {}", e.getMessage());
        }
    }

    // ------------------------------------------------------------------
    // Mapping helpers
    // ------------------------------------------------------------------

    private SessionStateSummaryEntity toEntity(SessionSummaryCreateRequest request) {
        SessionStateSummaryEntity entity = new SessionStateSummaryEntity();
        entity.setUserId(request.getUserId());
        entity.setTaskId(request.getTaskId());
        entity.setSessionSeq(request.getSessionSeq() != null ? request.getSessionSeq() : 1);
        entity.setTaskType(request.getTaskType());
        entity.setTaskGoal(request.getTaskGoal());
        entity.setKnowledgeState(toJson(request.getKnowledgeState()));
        entity.setUserContext(toJson(request.getUserContext()));
        entity.setExecutionState(toJson(request.getExecutionState()));
        entity.setSourcePreference(toJson(request.getSourcePreference()));
        entity.setIsDeleted(false);
        return entity;
    }

    private void updateEntityFromRequest(SessionStateSummaryEntity entity, SessionSummaryCreateRequest request) {
        if (request.getTaskType() != null) entity.setTaskType(request.getTaskType());
        if (request.getTaskGoal() != null) entity.setTaskGoal(request.getTaskGoal());
        if (request.getSessionSeq() != null) entity.setSessionSeq(request.getSessionSeq());
        if (request.getKnowledgeState() != null) entity.setKnowledgeState(toJson(request.getKnowledgeState()));
        if (request.getUserContext() != null) entity.setUserContext(toJson(request.getUserContext()));
        if (request.getExecutionState() != null) entity.setExecutionState(toJson(request.getExecutionState()));
        if (request.getSourcePreference() != null) entity.setSourcePreference(toJson(request.getSourcePreference()));
    }

    private String toJson(Object obj) {
        if (obj == null) return "{}";
        try {
            return objectMapper.writeValueAsString(obj);
        } catch (JsonProcessingException e) {
            log.warn("Failed to serialize object to JSON", e);
            return "{}";
        }
    }

    private String generateSummaryId() {
        return "ss_" + UUID.randomUUID().toString().replace("-", "").substring(0, 12);
    }
}
