package com.shardflow.profile.service.impl;

import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.shardflow.common.dto.ProfileUpdateRequest;
import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import com.shardflow.common.entity.ProfileEntity;
import com.shardflow.profile.repository.ProfileRepository;
import com.shardflow.profile.service.ProfileService;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.data.redis.core.RedisTemplate;
import org.springframework.stereotype.Service;

import java.time.Duration;
import java.time.Instant;
import java.util.Map;
import java.util.Optional;

@Slf4j
@Service
@RequiredArgsConstructor
public class ProfileServiceImpl implements ProfileService {

    private static final Duration CACHE_TTL = Duration.ofSeconds(3600);

    private final ProfileRepository repository;
    private final RedisTemplate<String, Object> redisTemplate;
    private final ObjectMapper objectMapper;

    @Override
    public Optional<ProfileEntity> getProfile(String userId) {
        String cacheKey = "shardflow:" + userId + ":profile:latest";
        Object cached = redisTemplate.opsForValue().get(cacheKey);
        if (cached != null) {
            try {
                return Optional.of(objectMapper.readValue(cached.toString(), ProfileEntity.class));
            } catch (JsonProcessingException e) {
                log.warn("Failed to deserialize cached profile for {}", userId);
            }
        }
        ProfileEntity profile = repository.selectOne(
            new LambdaQueryWrapper<ProfileEntity>().eq(ProfileEntity::getUserId, userId));
        if (profile != null) {
            cacheProfile(userId, profile);
        }
        return Optional.ofNullable(profile);
    }

    @Override
    public ProfileEntity upsertProfile(String userId, ProfileUpdateRequest request) {
        ProfileEntity profile = repository.selectOne(
            new LambdaQueryWrapper<ProfileEntity>().eq(ProfileEntity::getUserId, userId));
        if (profile == null) {
            profile = new ProfileEntity();
            profile.setUserId(userId);
        }

        if (request.preferences() != null) {
            try {
                profile.setPreferences(objectMapper.writeValueAsString(request.preferences()));
            } catch (JsonProcessingException e) {
                log.warn("Failed to serialize preferences for {}", userId);
            }
        }
        if (request.expertise() != null) {
            try {
                profile.setExpertise(objectMapper.writeValueAsString(request.expertise()));
            } catch (JsonProcessingException e) {
                log.warn("Failed to serialize expertise for {}", userId);
            }
        }
        if (request.habits() != null) {
            try {
                profile.setHabits(objectMapper.writeValueAsString(request.habits()));
            } catch (JsonProcessingException e) {
                log.warn("Failed to serialize habits for {}", userId);
            }
        }
        profile.setUpdatedAt(Instant.now());
        repository.updateById(profile);
        cacheProfile(userId, profile);
        return profile;
    }

    @Override
    public void updateFromCallback(String userId, Map<String, Object> updates) {
        ProfileEntity profile = repository.selectOne(
            new LambdaQueryWrapper<ProfileEntity>().eq(ProfileEntity::getUserId, userId));
        if (profile == null) {
            profile = new ProfileEntity();
            profile.setUserId(userId);
        }
        try {
            if (updates.containsKey("preferences")) {
                profile.setPreferences(objectMapper.writeValueAsString(updates.get("preferences")));
            }
            if (updates.containsKey("expertise")) {
                profile.setExpertise(objectMapper.writeValueAsString(updates.get("expertise")));
            }
            if (updates.containsKey("habits")) {
                profile.setHabits(objectMapper.writeValueAsString(updates.get("habits")));
            }
        } catch (JsonProcessingException e) {
            log.warn("Failed to serialize callback updates for {}", userId);
        }
        profile.setUpdatedAt(Instant.now());
        repository.updateById(profile);
        cacheProfile(userId, profile);
    }

    private void cacheProfile(String userId, ProfileEntity profile) {
        try {
            redisTemplate.opsForValue().set(
                "shardflow:" + userId + ":profile:latest",
                objectMapper.writeValueAsString(profile),
                CACHE_TTL
            );
        } catch (JsonProcessingException e) {
            log.warn("Failed to cache profile for {}", userId);
        }
    }
}
