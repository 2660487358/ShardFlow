package com.shardflow.profile.service;

import com.shardflow.common.dto.ProfileUpdateRequest;
import com.shardflow.common.entity.ProfileEntity;
import java.util.Map;
import java.util.Optional;

public interface ProfileService {

    Optional<ProfileEntity> getProfile(String userId);

    ProfileEntity upsertProfile(String userId, ProfileUpdateRequest request);

    void updateFromCallback(String userId, Map<String, Object> updates);
}
