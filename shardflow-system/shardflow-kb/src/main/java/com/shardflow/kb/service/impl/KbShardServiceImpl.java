package com.shardflow.kb.service.impl;

import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import com.baomidou.mybatisplus.core.conditions.update.LambdaUpdateWrapper;
import tools.jackson.core.JacksonException;
import tools.jackson.databind.ObjectMapper;
import com.shardflow.common.entity.KbShardEntity;
import com.shardflow.kb.repository.KbShardRepository;
import com.shardflow.kb.service.KbShardService;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.data.redis.core.RedisTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.time.Duration;
import java.util.*;

/**
 * 知识库状态包服务实现（C-4.5 通用 ContextShard 状态包）。
 * <p>
 * 规则条款：C-4.5（状态包管理）、C-6.5（版本号乐观锁）、C-3.4（三级存取）、C-4.8（回调接口）。
 * <p>
 * 实现要点：
 * 1. 创建时自动生成 shardId，version 初始化为 1。
 * 2. 更新时使用版本号乐观锁，版本不匹配则拒绝更新。
 * 3. 三级读取路径：L1 Redis → L2 PostgreSQL。
 * 4. 回调聚合：解析 Python 推理层回调请求，创建或更新状态包。
 */
@Slf4j
@Service
@RequiredArgsConstructor
public class KbShardServiceImpl implements KbShardService {

    private final KbShardRepository repository;
    private final RedisTemplate<String, Object> redisTemplate;
    private final ObjectMapper objectMapper;

    /** Redis Key 模式：shardflow:{owner_id}:shard:{shard_id} */
    private static final String REDIS_KEY_PATTERN = "shardflow:%s:shard:%s";
    private static final Duration REDIS_TTL = Duration.ofHours(24);

    @Override
    @Transactional
    public KbShardEntity createShard(KbShardEntity entity) {
        if (entity.getShardId() == null || entity.getShardId().isBlank()) {
            entity.setShardId(generateShardId());
        }
        if (entity.getVersion() == null) {
            entity.setVersion(1);
        }
        if (entity.getStatus() == null) {
            entity.setStatus("active");
        }
        if (entity.getIsDeleted() == null) {
            entity.setIsDeleted(false);
        }

        repository.insert(entity);
        syncToRedis(entity);

        log.info("Created kb_shard: shardId={}, owner={}, type={}, version={}",
                entity.getShardId(), entity.getOwnerId(), entity.getShardType(), entity.getVersion());
        return entity;
    }

    @Override
    public Optional<KbShardEntity> getShard(String shardId) {
        // L1 Redis 缓存
        KbShardEntity cached = loadFromRedis(shardId);
        if (cached != null) {
            return Optional.of(cached);
        }

        // L2 PostgreSQL
        KbShardEntity entity = repository.selectOne(
                new LambdaQueryWrapper<KbShardEntity>()
                        .eq(KbShardEntity::getShardId, shardId)
                        .eq(KbShardEntity::getIsDeleted, false));

        if (entity != null) {
            syncToRedis(entity);
        }
        return Optional.ofNullable(entity);
    }

    @Override
    public List<KbShardEntity> listByOwner(String ownerId, String shardType) {
        LambdaQueryWrapper<KbShardEntity> wrapper = new LambdaQueryWrapper<KbShardEntity>()
                .eq(KbShardEntity::getOwnerId, ownerId)
                .eq(KbShardEntity::getIsDeleted, false)
                .orderByDesc(KbShardEntity::getUpdatedAt);

        if (shardType != null && !shardType.isBlank()) {
            wrapper.eq(KbShardEntity::getShardType, shardType);
        }

        return repository.selectList(wrapper);
    }

    @Override
    @Transactional
    public Optional<KbShardEntity> updateShard(String shardId, KbShardEntity entity, Integer expectedVersion) {
        KbShardEntity existing = repository.selectOne(
                new LambdaQueryWrapper<KbShardEntity>()
                        .eq(KbShardEntity::getShardId, shardId)
                        .eq(KbShardEntity::getIsDeleted, false));

        if (existing == null) {
            return Optional.empty();
        }

        // 版本号乐观锁校验（C-6.5）
        if (expectedVersion != null && !expectedVersion.equals(existing.getVersion())) {
            log.warn("Optimistic lock conflict: shardId={}, expected={}, actual={}",
                    shardId, expectedVersion, existing.getVersion());
            return Optional.empty();
        }

        // 增量更新字段
        if (entity.getContext() != null) existing.setContext(entity.getContext());
        if (entity.getMemoryRefs() != null) existing.setMemoryRefs(entity.getMemoryRefs());
        if (entity.getStrategyHints() != null) existing.setStrategyHints(entity.getStrategyHints());
        if (entity.getRetrievedRefs() != null) existing.setRetrievedRefs(entity.getRetrievedRefs());
        if (entity.getStatus() != null) existing.setStatus(entity.getStatus());
        if (entity.getTaskId() != null) existing.setTaskId(entity.getTaskId());
        if (entity.getSessionId() != null) existing.setSessionId(entity.getSessionId());

        existing.setVersion(existing.getVersion() + 1);
        repository.updateById(existing);
        syncToRedis(existing);

        log.info("Updated kb_shard: shardId={}, version={}", shardId, existing.getVersion());
        return Optional.of(existing);
    }

    @Override
    @Transactional
    public Optional<KbShardEntity> archiveShard(String shardId) {
        KbShardEntity existing = repository.selectOne(
                new LambdaQueryWrapper<KbShardEntity>()
                        .eq(KbShardEntity::getShardId, shardId)
                        .eq(KbShardEntity::getIsDeleted, false));

        if (existing == null) {
            return Optional.empty();
        }

        existing.setStatus("archived");
        existing.setVersion(existing.getVersion() + 1);
        repository.updateById(existing);

        // 归档后从 Redis 移除（L1 不再缓存归档数据）
        invalidateRedis(existing.getOwnerId(), shardId);

        log.info("Archived kb_shard: shardId={}, version={}", shardId, existing.getVersion());
        return Optional.of(existing);
    }

    @Override
    @Transactional
    public boolean deleteShard(String shardId) {
        KbShardEntity existing = repository.selectOne(
                new LambdaQueryWrapper<KbShardEntity>()
                        .eq(KbShardEntity::getShardId, shardId)
                        .eq(KbShardEntity::getIsDeleted, false));

        if (existing == null) {
            return false;
        }

        int updated = repository.update(null,
                new LambdaUpdateWrapper<KbShardEntity>()
                        .eq(KbShardEntity::getShardId, shardId)
                        .set(KbShardEntity::getIsDeleted, true)
                        .set(KbShardEntity::getStatus, "deleted"));

        invalidateRedis(existing.getOwnerId(), shardId);

        log.info("Deleted kb_shard: shardId={}", shardId);
        return updated > 0;
    }

    @Override
    @Transactional
    @SuppressWarnings("unchecked")
    public Map<String, Object> saveFromCallback(Map<String, Object> body) {
        String shardId = (String) body.get("shard_id");
        String ownerId = (String) body.get("owner_id");
        String shardType = (String) body.getOrDefault("shard_type", "session");

        if (ownerId == null || ownerId.isBlank()) {
            return Map.of("success", false, "error", "owner_id is required");
        }

        KbShardEntity entity = new KbShardEntity();
        entity.setShardId(shardId);
        entity.setOwnerId(ownerId);
        entity.setShardType(shardType);
        entity.setTaskId((String) body.get("task_id"));
        entity.setSessionId((String) body.get("session_id"));

        // 序列化 JSONB 字段
        try {
            Object context = body.get("context");
            if (context != null) entity.setContext(objectMapper.writeValueAsString(context));

            Object memoryRefs = body.get("memory_refs");
            if (memoryRefs != null) entity.setMemoryRefs(objectMapper.writeValueAsString(memoryRefs));

            Object strategyHints = body.get("strategy_hints");
            if (strategyHints != null) entity.setStrategyHints(objectMapper.writeValueAsString(strategyHints));

            Object retrievedRefs = body.get("retrieved_refs");
            if (retrievedRefs != null) entity.setRetrievedRefs(objectMapper.writeValueAsString(retrievedRefs));
        } catch (JacksonException e) {
            log.warn("Failed to serialize kb_shard fields: {}", e.getMessage());
        }

        // 检查是否已存在（upsert 语义）
        if (shardId != null && !shardId.isBlank()) {
            Optional<KbShardEntity> existing = getShard(shardId);
            if (existing.isPresent()) {
                // 更新现有状态包
                Object versionObj = body.get("expected_version");
                Integer expectedVersion = (versionObj instanceof Number n) ? n.intValue() : null;
                Optional<KbShardEntity> updated = updateShard(shardId, entity, expectedVersion);
                if (updated.isPresent()) {
                    return Map.of(
                            "success", true,
                            "shard_id", updated.get().getShardId(),
                            "status", "updated",
                            "version", updated.get().getVersion()
                    );
                } else {
                    return Map.of(
                            "success", false,
                            "error", "Optimistic lock conflict",
                            "shard_id", shardId
                    );
                }
            }
        }

        // 创建新状态包
        KbShardEntity created = createShard(entity);
        return Map.of(
                "success", true,
                "shard_id", created.getShardId(),
                "status", "created",
                "version", created.getVersion()
        );
    }

    // ------------------------------------------------------------------
    // Redis 缓存（C-3.4 三级存取 L1）
    // ------------------------------------------------------------------

    private void syncToRedis(KbShardEntity entity) {
        try {
            String key = String.format(REDIS_KEY_PATTERN, entity.getOwnerId(), entity.getShardId());
            String json = objectMapper.writeValueAsString(entity);
            redisTemplate.opsForValue().set(key, json, REDIS_TTL);
        } catch (Exception e) {
            log.warn("Failed to sync kb_shard to Redis: {}", e.getMessage());
        }
    }

    private KbShardEntity loadFromRedis(String shardId) {
        try (org.springframework.data.redis.core.Cursor<byte[]> cursor = redisTemplate.getConnectionFactory()
                .getConnection()
                .keyCommands()
                .scan(org.springframework.data.redis.core.ScanOptions.scanOptions()
                        .match("shardflow:*:shard:" + shardId)
                        .count(100L)
                        .build())) {
            while (cursor.hasNext()) {
                String key = new String(cursor.next());
                Object raw = redisTemplate.opsForValue().get(key);
                if (raw instanceof String json) {
                    return objectMapper.readValue(json, KbShardEntity.class);
                }
            }
        } catch (Exception e) {
            log.debug("Redis cache miss for kb_shard {}: {}", shardId, e.getMessage());
        }
        return null;
    }

    private void invalidateRedis(String ownerId, String shardId) {
        try {
            String key = String.format(REDIS_KEY_PATTERN, ownerId, shardId);
            redisTemplate.delete(key);
        } catch (Exception e) {
            log.warn("Failed to invalidate kb_shard cache: {}", e.getMessage());
        }
    }

    private String generateShardId() {
        return "shard_" + UUID.randomUUID().toString().replace("-", "").substring(0, 12);
    }
}
