package com.shardflow.profile.controller;

import com.shardflow.common.dto.ProfileUpdateRequest;
import com.shardflow.common.dto.Result;
import com.shardflow.profile.service.ProfileService;
import jakarta.servlet.http.HttpServletRequest;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.*;
import org.springframework.web.server.ResponseStatusException;

import java.util.List;
import java.util.Map;

@Slf4j
@RestController
@RequiredArgsConstructor
public class ProfileController {

    private final ProfileService profileService;

    @Value("${shardflow.java-api-key:}")
    private String javaApiKey;

    private void checkApiKey(HttpServletRequest request) {
        if (javaApiKey == null || javaApiKey.isBlank()) {
            log.warn("java_api_key not configured, skipping API key validation");
            return;
        }
        String providedKey = request.getHeader("X-API-Key");
        if (providedKey == null || !javaApiKey.equals(providedKey)) {
            throw new ResponseStatusException(HttpStatus.UNAUTHORIZED, "Invalid or missing X-API-Key");
        }
    }

    @GetMapping("/api/v1/profile/{userId}")
    public Result<?> getProfile(@PathVariable String userId) {
        return profileService.getProfile(userId)
            .map(Result::ok)
            .orElse(Result.fail(404, "Profile not found"));
    }

    @PutMapping("/api/v1/profile/{userId}")
    public Result<?> upsertProfile(@PathVariable String userId,
                                   @RequestBody ProfileUpdateRequest request) {
        return Result.ok(profileService.upsertProfile(userId, request));
    }

    @PostMapping("/api/v1/callback/profile")
    public Result<Map<String, Object>> callbackProfile(@RequestBody Map<String, Object> body,
                                                        HttpServletRequest request) {
        checkApiKey(request);
        String userId = (String) body.get("user_id");
        @SuppressWarnings("unchecked")
        Map<String, Object> updates = (Map<String, Object>) body.get("updates");
        profileService.updateFromCallback(userId, updates);
        return Result.ok(Map.of("success", true, "profile_id", userId));
    }

    @GetMapping("/api/v1/profile/{userId}/history")
    public Result<Map<String, Object>> getProfileHistory(@PathVariable String userId) {
        return Result.ok(Map.of("user_id", userId, "history", List.of()));
    }
}
