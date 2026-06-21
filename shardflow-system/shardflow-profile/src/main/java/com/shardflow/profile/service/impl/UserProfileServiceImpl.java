package com.shardflow.profile.service.impl;

import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import com.baomidou.mybatisplus.core.conditions.update.LambdaUpdateWrapper;
import tools.jackson.core.JacksonException;
import tools.jackson.databind.ObjectMapper;
import com.shardflow.common.dto.profile.UserProfileUpdateRequest;
import com.shardflow.common.dto.profile.UserProfileUpdateResponse;
import com.shardflow.common.entity.UserProfileEntity;
import com.shardflow.common.entity.UserProfileHistoryEntity;
import com.shardflow.profile.repository.UserProfileHistoryRepository;
import com.shardflow.profile.repository.UserProfileRepository;
import com.shardflow.profile.service.UserProfileService;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.data.redis.core.RedisTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.time.Duration;
import java.time.Instant;
import java.util.HashMap;
import java.util.Map;
import java.util.Optional;

/**
 * 用户画像服务实现（S4.3 增强版）。
 * <p>
 * 规则条款：C-9.12（画像变更历史）、C-3.5（画像增量合并）、C-4.3（Pub/Sub 通知）。
 * <p>
 * 增强点：
 * 1. 增量合并（JSON Patch）：不再全量覆盖，而是将新字段合并到现有 JSON。
 * 2. Pub/Sub 通知：画像变更后发布到 Redis 频道 {@code shardflow:profile:changed}。
 * 3. 历史记录：每次变更写入 user_profile_history 表，记录 patch + 前后快照。
 *
 * Redis Key: shardflow:{userId}:profile:latest (TTL 60min)
 * Per Agent架构规则文档 and spec section 7.9.
 */
@Slf4j
@Service
@RequiredArgsConstructor
public class UserProfileServiceImpl implements UserProfileService {

    private final UserProfileRepository repository;
    private final UserProfileHistoryRepository historyRepository;
    private final RedisTemplate<String, Object> redisTemplate;
    private final ObjectMapper objectMapper;

    /** Redis key pattern for profile cache: shardflow:{userId}:profile:latest */
    private static final String REDIS_KEY_PATTERN = "shardflow:%s:profile:latest";
    private static final Duration REDIS_TTL = Duration.ofMinutes(60);

    /** Pub/Sub 频道：画像变更通知 */
    private static final String PROFILE_CHANGE_CHANNEL = "shardflow:profile:changed";

    @Override
    public Optional<UserProfileEntity> getProfile(String userId) {
        // Try Redis cache first (L1)
        UserProfileEntity cached = loadFromRedis(userId);
        if (cached != null) {
            return Optional.of(cached);
        }

        // Fall back to PostgreSQL (L2)
        UserProfileEntity entity = repository.selectOne(
                new LambdaQueryWrapper<UserProfileEntity>()
                        .eq(UserProfileEntity::getUserId, userId)
                        .isNull(UserProfileEntity::getDeletedAt));

        if (entity != null) {
            syncToRedis(entity);
        }
        return Optional.ofNullable(entity);
    }

    @Override
    @Transactional
    public UserProfileUpdateResponse updateProfile(String userId, UserProfileUpdateRequest request) {
        return updateProfileInternal(userId, request, "api", null);
    }

    @Override
    @Transactional
    public UserProfileUpdateResponse saveFromCallback(String userId, UserProfileUpdateRequest request) {
        return updateProfileInternal(userId, request, "callback", null);
    }

    /**
     * 内部更新逻辑：增量合并 + 历史记录 + Pub/Sub 通知。
     *
     * @param userId   用户ID
     * @param request  更新请求
     * @param source   变更来源（api/callback/system）
     * @param traceId  链路追踪ID
     */
    @SuppressWarnings("unchecked")
    private UserProfileUpdateResponse updateProfileInternal(
            String userId, UserProfileUpdateRequest request, String source, String traceId) {
        UserProfileEntity existing = repository.selectOne(
                new LambdaQueryWrapper<UserProfileEntity>()
                        .eq(UserProfileEntity::getUserId, userId)
                        .isNull(UserProfileEntity::getDeletedAt));

        if (existing != null) {
            // 保存变更前快照
            String beforeSnapshot = existing.getPreference() != null ? existing.getPreference() : "{}";
            String beforeHabits = existing.getInteractionHabits() != null ? existing.getInteractionHabits() : "{}";

            // 增量合并（JSON Patch）：将新字段合并到现有 JSON，而非全量覆盖
            Map<String, Object> patch = new HashMap<>();
            if (request.getPreference() != null) {
                String mergedPreference = mergeJson(existing.getPreference(), toJson(request.getPreference()), patch, "preference");
                existing.setPreference(mergedPreference);
            }
            if (request.getInteractionHabits() != null) {
                String mergedHabits = mergeJson(existing.getInteractionHabits(), toJson(request.getInteractionHabits()), patch, "interaction_habits");
                existing.setInteractionHabits(mergedHabits);
            }

            existing.setProfileVersion(existing.getProfileVersion() + 1);
            repository.updateById(existing);
            syncToRedis(existing);

            // 记录历史
            recordHistory(existing, "UPDATE", patch, beforeSnapshot, beforeHabits, source, traceId);

            // Pub/Sub 通知
            publishProfileChange(userId, existing.getProfileVersion(), "UPDATE");

            log.info("Updated user profile (incremental merge): userId={}, version={}, patchSize={}",
                    userId, existing.getProfileVersion(), patch.size());

            return new UserProfileUpdateResponse(
                    String.valueOf(existing.getProfileId()),
                    "updated",
                    existing.getProfileVersion());
        } else {
            // Create new profile
            UserProfileEntity entity = new UserProfileEntity();
            entity.setUserId(userId);
            entity.setProfileVersion(1);
            entity.setPreference(toJson(request.getPreference()));
            entity.setInteractionHabits(toJson(request.getInteractionHabits()));
            repository.insert(entity);
            syncToRedis(entity);

            // 记录历史
            Map<String, Object> patch = new HashMap<>();
            patch.put("preference", request.getPreference());
            patch.put("interaction_habits", request.getInteractionHabits());
            recordHistory(entity, "CREATE", patch, "{}", "{}", source, traceId);

            // Pub/Sub 通知
            publishProfileChange(userId, entity.getProfileVersion(), "CREATE");

            log.info("Created user profile: userId={}, profileId={}", userId, entity.getProfileId());

            return new UserProfileUpdateResponse(
                    String.valueOf(entity.getProfileId()),
                    "created",
                    entity.getProfileVersion());
        }
    }

    @Override
    @Transactional
    public boolean deleteProfile(String userId) {
        UserProfileEntity existing = repository.selectOne(
                new LambdaQueryWrapper<UserProfileEntity>()
                        .eq(UserProfileEntity::getUserId, userId)
                        .isNull(UserProfileEntity::getDeletedAt));

        int updated = repository.update(null,
                new LambdaUpdateWrapper<UserProfileEntity>()
                        .eq(UserProfileEntity::getUserId, userId)
                        .isNull(UserProfileEntity::getDeletedAt)
                        .set(UserProfileEntity::getDeletedAt, Instant.now()));

        removeFromRedis(userId);

        if (updated > 0 && existing != null) {
            // 记录删除历史
            Map<String, Object> patch = new HashMap<>();
            patch.put("deleted_at", Instant.now().toString());
            recordHistory(existing, "DELETE", patch, existing.getPreference(), existing.getInteractionHabits(), "api", null);

            // Pub/Sub 通知
            publishProfileChange(userId, existing.getProfileVersion(), "DELETE");

            log.info("Soft-deleted user profile: userId={}", userId);
        }
        return updated > 0;
    }

    // ------------------------------------------------------------------
    // 增量合并（JSON Patch）
    // ------------------------------------------------------------------

    /**
     * 将增量 JSON 合并到现有 JSON，并记录变更到 patch。
     *
     * @param existingJson 现有 JSON 字符串
     * @param newJson      新增 JSON 字符串
     * @param patch        变更记录载体（会被填充）
     * @param fieldPrefix  字段前缀（用于 patch key 命名）
     * @return 合并后的 JSON 字符串
     */
    @SuppressWarnings("unchecked")
    private String mergeJson(String existingJson, String newJson, Map<String, Object> patch, String fieldPrefix) {
        try {
            Map<String, Object> existing = (existingJson != null && !existingJson.isBlank())
                    ? objectMapper.readValue(existingJson, Map.class)
                    : new HashMap<>();
            Map<String, Object> update = (newJson != null && !newJson.isBlank())
                    ? objectMapper.readValue(newJson, Map.class)
                    : new HashMap<>();

            for (Map.Entry<String, Object> entry : update.entrySet()) {
                String key = entry.getKey();
                Object newVal = entry.getValue();
                Object oldVal = existing.get(key);

                // 仅记录实际变更的字段
                if (newVal != null && !newVal.equals(oldVal)) {
                    existing.put(key, newVal);
                    patch.put(fieldPrefix + "." + key, newVal);
                }
            }

            return objectMapper.writeValueAsString(existing);
        } catch (Exception e) {
            log.warn("Failed to merge JSON for {}: {}", fieldPrefix, e.getMessage());
            return newJson != null ? newJson : existingJson;
        }
    }

    // ------------------------------------------------------------------
    // 历史记录（C-9.12）
    // ------------------------------------------------------------------

    private void recordHistory(UserProfileEntity entity, String changeType,
                                Map<String, Object> patch, String beforePreference, String beforeHabits,
                                String source, String traceId) {
        try {
            UserProfileHistoryEntity history = new UserProfileHistoryEntity();
            history.setUserId(entity.getUserId());
            history.setProfileVersion(entity.getProfileVersion());
            history.setChangeType(changeType);
            history.setPatch(objectMapper.writeValueAsString(patch));
            history.setBeforeSnapshot(buildSnapshot(beforePreference, beforeHabits));
            history.setAfterSnapshot(buildSnapshot(entity.getPreference(), entity.getInteractionHabits()));
            history.setSource(source);
            history.setTraceId(traceId);
            historyRepository.insert(history);
            log.debug("Profile history recorded: user={}, version={}, type={}",
                    entity.getUserId(), entity.getProfileVersion(), changeType);
        } catch (Exception e) {
            log.warn("Failed to record profile history: {}", e.getMessage());
        }
    }

    private String buildSnapshot(String preference, String habits) {
        try {
            Map<String, Object> snapshot = new HashMap<>();
            snapshot.put("preference", preference != null ? objectMapper.readValue(preference, Map.class) : Map.of());
            snapshot.put("interaction_habits", habits != null ? objectMapper.readValue(habits, Map.class) : Map.of());
            return objectMapper.writeValueAsString(snapshot);
        } catch (Exception e) {
            return "{}";
        }
    }

    // ------------------------------------------------------------------
    // Pub/Sub 通知（C-4.3）
    // ------------------------------------------------------------------

    private void publishProfileChange(String userId, Integer version, String changeType) {
        try {
            Map<String, Object> event = new HashMap<>();
            event.put("user_id", userId);
            event.put("profile_version", version);
            event.put("change_type", changeType);
            event.put("timestamp", Instant.now().toString());
            String message = objectMapper.writeValueAsString(event);
            redisTemplate.convertAndSend(PROFILE_CHANGE_CHANNEL, message);
            log.debug("Published profile change event: channel={}, user={}, version={}",
                    PROFILE_CHANGE_CHANNEL, userId, version);
        } catch (Exception e) {
            log.warn("Failed to publish profile change event: {}", e.getMessage());
        }
    }

    // ------------------------------------------------------------------
    // Redis cache sync (P3.2.4)
    // ------------------------------------------------------------------

    private void syncToRedis(UserProfileEntity entity) {
        try {
            String key = String.format(REDIS_KEY_PATTERN, entity.getUserId());
            String json = objectMapper.writeValueAsString(entity);
            redisTemplate.opsForValue().set(key, json, REDIS_TTL);
            log.debug("Synced profile to Redis: key={}", key);
        } catch (JacksonException e) {
            log.warn("Failed to sync profile to Redis: {}", e.getMessage());
        }
    }

    private UserProfileEntity loadFromRedis(String userId) {
        try {
            String key = String.format(REDIS_KEY_PATTERN, userId);
            Object raw = redisTemplate.opsForValue().get(key);
            if (raw instanceof String json) {
                return objectMapper.readValue(json, UserProfileEntity.class);
            }
        } catch (Exception e) {
            log.debug("Redis cache miss for profile {}: {}", userId, e.getMessage());
        }
        return null;
    }

    private void removeFromRedis(String userId) {
        try {
            String key = String.format(REDIS_KEY_PATTERN, userId);
            redisTemplate.delete(key);
        } catch (Exception e) {
            log.warn("Failed to remove profile from Redis: {}", e.getMessage());
        }
    }

    // ------------------------------------------------------------------
    // Mapping helpers
    // ------------------------------------------------------------------

    private String toJson(Object obj) {
        if (obj == null) return "{}";
        try {
            return objectMapper.writeValueAsString(obj);
        } catch (JacksonException e) {
            log.warn("Failed to serialize object to JSON", e);
            return "{}";
        }
    }
}
