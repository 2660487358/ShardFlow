package com.shardflow.profile.service;

import com.shardflow.common.dto.profile.UserProfileUpdateRequest;
import com.shardflow.common.dto.profile.UserProfileUpdateResponse;
import com.shardflow.common.entity.UserProfileEntity;

import java.util.Optional;

/**
 * User profile service interface.
 * Provides CRUD operations and cache management for user profiles.
 * Per spec section 7.9 and FR-SM-002.
 */
public interface UserProfileService {

    /**
     * Get user profile by user ID.
     * Per spec: GET /api/v1/profile/{userId}
     */
    Optional<UserProfileEntity> getProfile(String userId);

    /**
     * Create or update user profile.
     * Per spec: PUT /api/v1/profile/{userId}
     */
    UserProfileUpdateResponse updateProfile(String userId, UserProfileUpdateRequest request);

    /**
     * Save profile from callback (Python推理层回调).
     * Per spec: POST /api/v1/callback/profile
     * Creates or updates based on user_id.
     */
    UserProfileUpdateResponse saveFromCallback(String userId, UserProfileUpdateRequest request);

    /**
     * Soft-delete user profile (per 被遗忘权).
     */
    boolean deleteProfile(String userId);
}
