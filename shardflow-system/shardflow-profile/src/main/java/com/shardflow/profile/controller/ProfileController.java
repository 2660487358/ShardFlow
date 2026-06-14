package com.shardflow.profile.controller;

import com.shardflow.common.dto.Result;
import com.shardflow.common.dto.profile.UserProfileUpdateRequest;
import com.shardflow.common.dto.profile.UserProfileUpdateResponse;
import com.shardflow.common.entity.UserProfileEntity;
import com.shardflow.profile.service.UserProfileService;
import com.shardflow.usercontext.context.UserContext;
import jakarta.servlet.http.HttpServletRequest;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.*;
import org.springframework.web.server.ResponseStatusException;

/**
 * REST API for user profile management.
 *
 * Endpoints per spec section 7.9:
 * - GET /api/v1/profile/{userId}  — Get user profile
 * - PUT /api/v1/profile/{userId}  — Create or update user profile
 * - DELETE /api/v1/profile/{userId} — Soft-delete user profile (被遗忘权)
 */
@Slf4j
@RestController
@RequestMapping("/api/v1/profile")
@RequiredArgsConstructor
public class ProfileController {

    private final UserProfileService profileService;

    @Value("${shardflow.java-api-key:}")
    private String javaApiKey;

    private void checkApiKey(HttpServletRequest request) {
        if (javaApiKey == null || javaApiKey.isBlank()) {
            return; // Skip validation if not configured
        }
        String providedKey = request.getHeader("X-API-Key");
        if (providedKey == null || !javaApiKey.equals(providedKey)) {
            throw new ResponseStatusException(HttpStatus.UNAUTHORIZED, "Invalid or missing X-API-Key");
        }
    }

    /**
     * GET /api/v1/profile/{userId} — Get user profile.
     * Per spec section 7.9.
     */
    @GetMapping("/{userId}")
    public Result<UserProfileEntity> getProfile(@PathVariable String userId) {
        return profileService.getProfile(userId)
                .map(Result::ok)
                .orElse(Result.fail(404, "Profile not found"));
    }

    /**
     * PUT /api/v1/profile/{userId} — Create or update user profile.
     * Per spec section 7.9.
     */
    @PutMapping("/{userId}")
    public Result<UserProfileUpdateResponse> updateProfile(
            @PathVariable String userId,
            @RequestBody UserProfileUpdateRequest request,
            HttpServletRequest httpRequest) {
        checkApiKey(httpRequest);
        return Result.ok(profileService.updateProfile(userId, request));
    }

    /**
     * DELETE /api/v1/profile/{userId} — Soft-delete user profile.
     * Per 被遗忘权 (spec section 9.6).
     */
    @DeleteMapping("/{userId}")
    public Result<Void> deleteProfile(
            @PathVariable String userId,
            HttpServletRequest httpRequest) {
        checkApiKey(httpRequest);
        boolean deleted = profileService.deleteProfile(userId);
        return deleted ? Result.ok() : Result.fail(404, "Profile not found");
    }
}
