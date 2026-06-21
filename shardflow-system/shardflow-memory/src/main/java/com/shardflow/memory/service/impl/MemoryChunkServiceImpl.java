package com.shardflow.memory.service.impl;

import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import com.baomidou.mybatisplus.core.conditions.update.LambdaUpdateWrapper;
import com.baomidou.mybatisplus.extension.plugins.pagination.Page;
import tools.jackson.core.JacksonException;
import tools.jackson.databind.ObjectMapper;
import com.shardflow.common.dto.memory.MemoryCreateRequest;
import com.shardflow.common.dto.memory.MemoryCreateResponse;
import com.shardflow.common.dto.memory.MemorySearchRequest;
import com.shardflow.common.dto.memory.MemorySearchResponse;
import com.shardflow.common.dto.memory.MemoryUpdateResponse;
import com.shardflow.common.entity.MemoryChunkEntity;
import com.shardflow.memory.repository.MemoryChunkRepository;
import com.shardflow.memory.service.MemoryChunkService;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.data.redis.core.Cursor;
import org.springframework.data.redis.core.RedisTemplate;
import org.springframework.data.redis.core.ScanOptions;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.math.BigDecimal;
import java.time.Duration;
import java.time.Instant;
import java.util.*;
import java.util.stream.Collectors;

@Slf4j
@Service
@RequiredArgsConstructor
public class MemoryChunkServiceImpl implements MemoryChunkService {

    private final MemoryChunkRepository repository;
    private final RedisTemplate<String, Object> redisTemplate;
    private final ObjectMapper objectMapper;

    /**
     * Redis key pattern for memory cache (FIX-KEY-1: 4段格式)。
     * <p>
     * 格式：shardflow:{user_id}:mem:{memory_type}:{chunkId}
     * 与 Python 推理层 redis_adapter.py 保持一致，确保 L1 缓存跨端共享（G-1/G-6 修复）。
     */
    private static final String REDIS_KEY_PATTERN = "shardflow:%s:mem:%s:%s";
    private static final Duration REDIS_TTL = Duration.ofMinutes(30);

    /** SCAN 单次匹配数（C-8.5 禁用 KEYS，使用 SCAN） */
    private static final long SCAN_COUNT = 100L;

    @Override
    @Transactional
    public MemoryCreateResponse createMemory(MemoryCreateRequest request) {
        // Conflict detection: check for same userId+category+contentText duplicates
        boolean conflictDetected = false;
        String conflictWith = null;
        if (request.getContent() != null && request.getContent().getText() != null) {
            MemoryChunkEntity duplicate = repository.selectOne(
                    new LambdaQueryWrapper<MemoryChunkEntity>()
                            .eq(MemoryChunkEntity::getUserId, request.getUserId())
                            .eq(MemoryChunkEntity::getCategory, request.getCategory())
                            .eq(MemoryChunkEntity::getContentText, request.getContent().getText())
                            .eq(MemoryChunkEntity::getIsDeleted, false)
                            .last("LIMIT 1"));
            if (duplicate != null) {
                conflictDetected = true;
                conflictWith = duplicate.getChunkId();
                log.info("Conflict detected: new memory conflicts with chunkId={}", conflictWith);
            }
        }

        MemoryChunkEntity entity = toEntity(request);
        entity.setChunkId(generateChunkId());
        entity.setIsDeleted(false);
        entity.setHasConflict(conflictDetected);
        entity.setConflictWith(conflictWith);
        if (conflictDetected) {
            entity.setResolutionStatus("pending");
        }
        repository.insert(entity);

        // Sync to Redis cache
        syncToRedis(entity);

        log.info("Created memory chunk: chunkId={}, userId={}, category={}, conflict={}",
                entity.getChunkId(), entity.getUserId(), entity.getCategory(), conflictDetected);

        MemoryCreateResponse response = new MemoryCreateResponse();
        response.setMemoryId(entity.getChunkId());
        response.setStatus("created");
        response.setConflictDetected(conflictDetected);
        response.setCreatedAt(entity.getCreatedAt());
        return response;
    }

    @Override
    public Optional<MemoryChunkEntity> getMemory(String chunkId) {
        // Try Redis cache first
        MemoryChunkEntity cached = loadFromRedis(chunkId);
        if (cached != null) {
            return Optional.of(cached);
        }

        MemoryChunkEntity entity = repository.selectOne(
                new LambdaQueryWrapper<MemoryChunkEntity>()
                        .eq(MemoryChunkEntity::getChunkId, chunkId)
                        .eq(MemoryChunkEntity::getIsDeleted, false));

        if (entity != null) {
            syncToRedis(entity);
        }
        return Optional.ofNullable(entity);
    }

    @Override
    @Transactional
    public MemoryUpdateResponse updateMemory(String chunkId, MemoryCreateRequest request) {
        MemoryChunkEntity existing = repository.selectOne(
                new LambdaQueryWrapper<MemoryChunkEntity>()
                        .eq(MemoryChunkEntity::getChunkId, chunkId)
                        .eq(MemoryChunkEntity::getIsDeleted, false));

        if (existing == null) {
            return null;
        }

        // Update fields from request
        updateEntityFromRequest(existing, request);
        repository.updateById(existing);

        // Sync to Redis cache
        syncToRedis(existing);

        log.info("Updated memory chunk: chunkId={}", chunkId);

        MemoryUpdateResponse response = new MemoryUpdateResponse();
        response.setMemoryId(chunkId);
        response.setStatus("updated");
        response.setUpdatedAt(existing.getUpdatedAt());
        return response;
    }

    @Override
    @Transactional
    public boolean deleteMemory(String chunkId) {
        // Get entity first to remove from Redis
        MemoryChunkEntity entity = repository.selectOne(
                new LambdaQueryWrapper<MemoryChunkEntity>()
                        .eq(MemoryChunkEntity::getChunkId, chunkId)
                        .eq(MemoryChunkEntity::getIsDeleted, false));

        if (entity == null) {
            return false;
        }

        int updated = repository.update(null,
                new LambdaUpdateWrapper<MemoryChunkEntity>()
                        .eq(MemoryChunkEntity::getChunkId, chunkId)
                        .set(MemoryChunkEntity::getIsDeleted, true));

        removeFromRedis(entity.getUserId(), entity.getMemoryType(), chunkId);

        return updated > 0;
    }

    @Override
    public MemorySearchResponse searchMemory(MemorySearchRequest request) {
        long startTime = System.currentTimeMillis();

        LambdaQueryWrapper<MemoryChunkEntity> wrapper = new LambdaQueryWrapper<MemoryChunkEntity>()
                .eq(MemoryChunkEntity::getUserId, request.getUserId())
                .eq(MemoryChunkEntity::getIsDeleted, false);

        // Apply filters
        if (request.getFilters() != null) {
            MemorySearchRequest.SearchFilters filters = request.getFilters();
            if (filters.getMemoryType() != null && !filters.getMemoryType().isEmpty()) {
                wrapper.in(MemoryChunkEntity::getMemoryType, filters.getMemoryType());
            }
            if (filters.getCategory() != null && !filters.getCategory().isEmpty()) {
                wrapper.in(MemoryChunkEntity::getCategory, filters.getCategory());
            }
            if (filters.getMinConfidence() != null) {
                wrapper.ge(MemoryChunkEntity::getConfidence, BigDecimal.valueOf(filters.getMinConfidence()));
            }
            if (filters.getCreatedAfter() != null && !filters.getCreatedAfter().isBlank()) {
                Instant after = Instant.parse(filters.getCreatedAfter());
                wrapper.ge(MemoryChunkEntity::getCreatedAt, after);
            }
            if (filters.getCreatedBefore() != null && !filters.getCreatedBefore().isBlank()) {
                Instant before = Instant.parse(filters.getCreatedBefore());
                wrapper.le(MemoryChunkEntity::getCreatedAt, before);
            }
        }

        // Text search on contentText if query is provided
        if (request.getQuery() != null && !request.getQuery().isBlank()) {
            wrapper.like(MemoryChunkEntity::getContentText, request.getQuery());
        }

        wrapper.orderByDesc(MemoryChunkEntity::getCreatedAt);

        int topK = request.getTopK() != null ? request.getTopK() : 10;
        Page<MemoryChunkEntity> page = repository.selectPage(
                new Page<>(1, topK), wrapper);

        List<MemorySearchResponse.MemoryResultItem> results = page.getRecords().stream()
                .map(this::toResultItem)
                .collect(Collectors.toList());

        long searchTimeMs = System.currentTimeMillis() - startTime;

        MemorySearchResponse response = new MemorySearchResponse();
        response.setResults(results);
        response.setTotal((int) page.getTotal());
        response.setSearchTimeMs(searchTimeMs);
        return response;
    }

    @Override
    public Map<String, Object> exportMemory(String userId) {
        List<MemoryChunkEntity> chunks = repository.selectList(
                new LambdaQueryWrapper<MemoryChunkEntity>()
                        .eq(MemoryChunkEntity::getUserId, userId)
                        .eq(MemoryChunkEntity::getIsDeleted, false)
                        .orderByDesc(MemoryChunkEntity::getCreatedAt));

        return Map.of(
                "user_id", userId,
                "memories", chunks,
                "total", chunks.size(),
                "exported_at", Instant.now().toString()
        );
    }

    @Override
    @Transactional
    @SuppressWarnings("unchecked")
    public MemoryCreateResponse saveFromCallback(Map<String, Object> body) {
        MemoryCreateRequest request = new MemoryCreateRequest();
        request.setUserId((String) body.get("user_id"));
        request.setMemoryType((String) body.get("memory_type"));
        request.setCategory((String) body.get("category"));
        request.setSource((String) body.get("source"));
        request.setSessionId((String) body.get("session_id"));

        Object confidenceObj = body.get("confidence");
        if (confidenceObj instanceof Number) {
            request.setConfidence(((Number) confidenceObj).doubleValue());
        }

        // Map content
        Object contentObj = body.get("content");
        if (contentObj instanceof Map) {
            Map<String, Object> contentMap = (Map<String, Object>) contentObj;
            MemoryCreateRequest.ContentPayload content = new MemoryCreateRequest.ContentPayload();
            content.setText((String) contentMap.get("text"));
            if (contentMap.get("structured") instanceof Map) {
                content.setStructured((Map<String, Object>) contentMap.get("structured"));
            }
            request.setContent(content);
        }

        // Map metadata
        Object metadataObj = body.get("metadata");
        if (metadataObj instanceof Map) {
            request.setMetadata((Map<String, Object>) metadataObj);
        }

        // Check if a memory already exists for this user+category+content
        if (request.getContent() != null && request.getContent().getText() != null) {
            MemoryChunkEntity existing = repository.selectOne(
                    new LambdaQueryWrapper<MemoryChunkEntity>()
                            .eq(MemoryChunkEntity::getUserId, request.getUserId())
                            .eq(MemoryChunkEntity::getCategory, request.getCategory())
                            .eq(MemoryChunkEntity::getContentText, request.getContent().getText())
                            .eq(MemoryChunkEntity::getIsDeleted, false)
                            .last("LIMIT 1"));

            if (existing != null) {
                // Update existing
                updateEntityFromRequest(existing, request);
                repository.updateById(existing);
                syncToRedis(existing);

                log.info("Callback updated memory: chunkId={}", existing.getChunkId());

                MemoryCreateResponse response = new MemoryCreateResponse();
                response.setMemoryId(existing.getChunkId());
                response.setStatus("updated");
                response.setConflictDetected(false);
                response.setCreatedAt(existing.getUpdatedAt());
                return response;
            }
        }

        // Create new
        return createMemory(request);
    }

    // ------------------------------------------------------------------
    // 冲突解决 API（C-3.3）
    // ------------------------------------------------------------------

    @Override
    public List<MemoryChunkEntity> listPendingConflicts(String userId) {
        return repository.selectList(
                new LambdaQueryWrapper<MemoryChunkEntity>()
                        .eq(MemoryChunkEntity::getUserId, userId)
                        .eq(MemoryChunkEntity::getHasConflict, true)
                        .eq(MemoryChunkEntity::getResolutionStatus, "pending")
                        .eq(MemoryChunkEntity::getIsDeleted, false)
                        .orderByDesc(MemoryChunkEntity::getCreatedAt));
    }

    @Override
    @Transactional
    public Optional<MemoryChunkEntity> resolveConflict(String chunkId, String resolution, String resolvedContent) {
        MemoryChunkEntity entity = repository.selectOne(
                new LambdaQueryWrapper<MemoryChunkEntity>()
                        .eq(MemoryChunkEntity::getChunkId, chunkId)
                        .eq(MemoryChunkEntity::getIsDeleted, false));

        if (entity == null) {
            return Optional.empty();
        }

        if (!Boolean.TRUE.equals(entity.getHasConflict())) {
            log.warn("Memory chunk {} has no conflict to resolve", chunkId);
            return Optional.of(entity);
        }

        switch (resolution.toUpperCase()) {
            case "KEEP_NEW" -> {
                // 保留当前内容（新内容已写入），仅标记冲突已解决
                entity.setHasConflict(false);
                entity.setResolutionStatus("resolved_keep_new");
                entity.setConflictWith(null);
            }
            case "KEEP_OLD" -> {
                // 恢复为旧内容（如果冲突对象存在）
                if (entity.getConflictWith() != null) {
                    MemoryChunkEntity oldEntity = repository.selectOne(
                            new LambdaQueryWrapper<MemoryChunkEntity>()
                                    .eq(MemoryChunkEntity::getChunkId, entity.getConflictWith())
                                    .eq(MemoryChunkEntity::getIsDeleted, false));
                    if (oldEntity != null) {
                        entity.setContentText(oldEntity.getContentText());
                        entity.setContentStructured(oldEntity.getContentStructured());
                    }
                }
                entity.setHasConflict(false);
                entity.setResolutionStatus("resolved_keep_old");
                entity.setConflictWith(null);
            }
            case "MERGE" -> {
                // 使用合并后的内容
                if (resolvedContent != null && !resolvedContent.isBlank()) {
                    entity.setContentText(resolvedContent);
                }
                entity.setHasConflict(false);
                entity.setResolutionStatus("resolved_merged");
                entity.setConflictWith(null);
            }
            default -> {
                log.warn("Unknown conflict resolution strategy: {}", resolution);
                return Optional.of(entity);
            }
        }

        repository.updateById(entity);
        syncToRedis(entity);
        log.info("Conflict resolved: chunkId={}, strategy={}", chunkId, resolution);
        return Optional.of(entity);
    }

    // ------------------------------------------------------------------
    // Redis cache sync (FIX-KEY-1: 4段格式 + SCAN 替代 KEYS)
    // ------------------------------------------------------------------

    private void syncToRedis(MemoryChunkEntity entity) {
        try {
            String key = buildRedisKey(entity.getUserId(), entity.getMemoryType(), entity.getChunkId());
            String json = objectMapper.writeValueAsString(entity);
            redisTemplate.opsForValue().set(key, json, REDIS_TTL);
            log.debug("Synced memory to Redis: key={}", key);
        } catch (JacksonException e) {
            log.warn("Failed to sync memory to Redis: {}", e.getMessage());
        }
    }

    private MemoryChunkEntity loadFromRedis(String chunkId) {
        // C-8.5: 使用 SCAN 替代 KEYS 命令，避免阻塞 Redis
        // 扫描模式：shardflow:*:mem:*:{chunkId}
        String scanPattern = "shardflow:*:mem:*:" + chunkId;
        try (Cursor<byte[]> cursor = redisTemplate.getConnectionFactory()
                .getConnection()
                .keyCommands()
                .scan(ScanOptions.scanOptions().match(scanPattern).count(SCAN_COUNT).build())) {
            while (cursor.hasNext()) {
                String key = new String(cursor.next());
                Object raw = redisTemplate.opsForValue().get(key);
                if (raw instanceof String json) {
                    return objectMapper.readValue(json, MemoryChunkEntity.class);
                }
            }
        } catch (Exception e) {
            log.debug("Redis cache miss for memory {}: {}", chunkId, e.getMessage());
        }
        return null;
    }

    private void removeFromRedis(String userId, String memoryType, String chunkId) {
        try {
            // 优先按 4 段格式精确删除
            String key = buildRedisKey(userId, memoryType, chunkId);
            redisTemplate.delete(key);
        } catch (Exception e) {
            log.warn("Failed to remove memory from Redis: {}", e.getMessage());
        }
    }

    /**
     * 构造 4 段格式 Redis Key：shardflow:{user_id}:mem:{memory_type}:{chunkId}
     */
    private String buildRedisKey(String userId, String memoryType, String chunkId) {
        String mt = (memoryType != null && !memoryType.isBlank()) ? memoryType : "UNKNOWN";
        return String.format(REDIS_KEY_PATTERN, userId, mt, chunkId);
    }

    // ------------------------------------------------------------------
    // Mapping helpers
    // ------------------------------------------------------------------

    private MemoryChunkEntity toEntity(MemoryCreateRequest request) {
        MemoryChunkEntity entity = new MemoryChunkEntity();
        entity.setUserId(request.getUserId());
        entity.setMemoryType(request.getMemoryType());
        entity.setCategory(request.getCategory());
        entity.setConfidence(request.getConfidence() != null
                ? BigDecimal.valueOf(request.getConfidence()) : null);
        entity.setSource(request.getSource());
        entity.setSourceSessionId(request.getSessionId());
        entity.setMetadata(toJson(request.getMetadata()));
        entity.setIsDeleted(false);

        if (request.getContent() != null) {
            entity.setContentText(request.getContent().getText());
            entity.setContentStructured(toJson(request.getContent().getStructured()));
        }

        return entity;
    }

    private void updateEntityFromRequest(MemoryChunkEntity entity, MemoryCreateRequest request) {
        if (request.getMemoryType() != null) entity.setMemoryType(request.getMemoryType());
        if (request.getCategory() != null) entity.setCategory(request.getCategory());
        if (request.getConfidence() != null) entity.setConfidence(BigDecimal.valueOf(request.getConfidence()));
        if (request.getSource() != null) entity.setSource(request.getSource());
        if (request.getSessionId() != null) entity.setSourceSessionId(request.getSessionId());
        if (request.getMetadata() != null) entity.setMetadata(toJson(request.getMetadata()));
        if (request.getContent() != null) {
            if (request.getContent().getText() != null) entity.setContentText(request.getContent().getText());
            if (request.getContent().getStructured() != null) entity.setContentStructured(toJson(request.getContent().getStructured()));
        }
    }

    private MemorySearchResponse.MemoryResultItem toResultItem(MemoryChunkEntity entity) {
        MemorySearchResponse.MemoryResultItem item = new MemorySearchResponse.MemoryResultItem();
        item.setMemoryId(entity.getChunkId());
        item.setContent(entity.getContentText());
        item.setConfidence(entity.getConfidence() != null ? entity.getConfidence().doubleValue() : null);
        item.setCategory(entity.getCategory());
        item.setMetadata(parseJsonToMap(entity.getMetadata()));
        return item;
    }

    private String toJson(Object obj) {
        if (obj == null) return null;
        try {
            return objectMapper.writeValueAsString(obj);
        } catch (JacksonException e) {
            log.warn("Failed to serialize object to JSON", e);
            return null;
        }
    }

    @SuppressWarnings("unchecked")
    private Map<String, Object> parseJsonToMap(String json) {
        if (json == null || json.isBlank()) return null;
        try {
            return objectMapper.readValue(json, Map.class);
        } catch (JacksonException e) {
            log.debug("Failed to parse JSON to Map", e);
            return null;
        }
    }

    private String generateChunkId() {
        return "mem_" + UUID.randomUUID().toString().replace("-", "").substring(0, 12);
    }
}
