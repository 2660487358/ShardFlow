package com.shardflow.profile.service.impl;

import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import com.baomidou.mybatisplus.core.conditions.update.LambdaUpdateWrapper;
import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.shardflow.common.dto.profile.UserProfileUpdateRequest;
import com.shardflow.common.dto.profile.UserProfileUpdateResponse;
import com.shardflow.common.entity.UserProfileEntity;
import com.shardflow.profile.repository.UserProfileRepository;
import com.shardflow.profile.service.UserProfileService;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.data.redis.core.RedisTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.time.Duration;
import java.time.Instant;
import java.util.Optional;

/**
 * User profile service implementation.
 * Manages UserProfile CRUD with Redis cache synchronization.
 *
 * Redis Key: shardflow:{userId}:profile:latest (TTL 60min)
 * Per Agent架构规则文档 and spec section 7.9.
 */
@Slf4j
@Service
@RequiredArgsConstructor
public class UserProfileServiceImpl implements UserProfileService {

    private final UserProfileRepository repository;
    private final RedisTemplate<String, Object> redisTemplate;
    private final ObjectMapper objectMapper;

    /** Redis key pattern for profile cache: shardflow:{userId}:profile:latest */
    private static final String REDIS_KEY_PATTERN = "shardflow:%s:profile:latest";
    private static final Duration REDIS_TTL = Duration.ofMinutes(60);

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
        UserProfileEntity existing = repository.selectOne(
                new LambdaQueryWrapper<UserProfileEntity>()
                        .eq(UserProfileEntity::getUserId, userId)
                        .isNull(UserProfileEntity::getDeletedAt));

        if (existing != null) {
            // Update existing profile
            updateEntityFromRequest(existing, request);
            existing.setProfileVersion(existing.getProfileVersion() + 1);
            repository.updateById(existing);
            syncToRedis(existing);

            log.info("Updated user profile: userId={}, version={}", userId, existing.getProfileVersion());

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

            log.info("Created user profile: userId={}, profileId={}", userId, entity.getProfileId());

            return new UserProfileUpdateResponse(
                    String.valueOf(entity.getProfileId()),
                    "created",
                    entity.getProfileVersion());
        }
    }

    @Override
    @Transactional
    public UserProfileUpdateResponse saveFromCallback(String userId, UserProfileUpdateRequest request) {
        // Delegate to updateProfile — same create-or-update logic
        return updateProfile(userId, request);
    }

    @Override
    @Transactional
    public boolean deleteProfile(String userId) {
        // Soft delete: set deletedAt timestamp
        int updated = repository.update(null,
                new LambdaUpdateWrapper<UserProfileEntity>()
                        .eq(UserProfileEntity::getUserId, userId)
                        .isNull(UserProfileEntity::getDeletedAt)
                        .set(UserProfileEntity::getDeletedAt, Instant.now()));

        // Remove from Redis cache
        removeFromRedis(userId);

        if (updated > 0) {
            log.info("Soft-deleted user profile: userId={}", userId);
        }
        return updated > 0;
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
        } catch (JsonProcessingException e) {
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

    private void updateEntityFromRequest(UserProfileEntity entity, UserProfileUpdateRequest request) {
        if (request.getPreference() != null) {
            entity.setPreference(toJson(request.getPreference()));
        }
        if (request.getInteractionHabits() != null) {
            entity.setInteractionHabits(toJson(request.getInteractionHabits()));
        }
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
}
