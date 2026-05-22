package com.shardflow.profile.service;

import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.shardflow.common.dto.ProfileUpdateRequest;
import com.shardflow.common.entity.ProfileEntity;
import com.shardflow.profile.repository.ProfileRepository;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.data.redis.core.RedisTemplate;
import org.springframework.stereotype.Service;

import java.time.Duration;
import java.time.Instant;
import java.util.Map;
import java.util.Optional;

@Service
public class ProfileService {
    private static final Logger log = LoggerFactory.getLogger(ProfileService.class);
    private static final Duration CACHE_TTL = Duration.ofSeconds(3600);

    private final ProfileRepository repository;
    private final RedisTemplate<String, Object> redisTemplate;
    private final ObjectMapper objectMapper;

    public ProfileService(ProfileRepository repository,
                          RedisTemplate<String, Object> redisTemplate,
                          ObjectMapper objectMapper) {
        this.repository = repository;
        this.redisTemplate = redisTemplate;
        this.objectMapper = objectMapper;
    }

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
        Optional<ProfileEntity> profile = repository.findById(userId);
        profile.ifPresent(p -> cacheProfile(userId, p));
        return profile;
    }

    public ProfileEntity upsertProfile(String userId, ProfileUpdateRequest request) {
        ProfileEntity profile = repository.findById(userId).orElseGet(() -> {
            ProfileEntity p = new ProfileEntity();
            p.setUserId(userId);
            return p;
        });

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
        ProfileEntity saved = repository.save(profile);
        cacheProfile(userId, saved);
        return saved;
    }

    public void updateFromCallback(String userId, Map<String, Object> updates) {
        ProfileEntity profile = repository.findById(userId).orElseGet(() -> {
            ProfileEntity p = new ProfileEntity();
            p.setUserId(userId);
            return p;
        });
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
        repository.save(profile);
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
