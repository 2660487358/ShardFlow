package com.shardflow.profile.controller;

import com.shardflow.common.dto.ProfileUpdateRequest;
import com.shardflow.common.entity.ProfileEntity;
import com.shardflow.profile.service.ProfileService;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

import java.util.Map;

@RestController
public class ProfileController {

    private final ProfileService profileService;

    public ProfileController(ProfileService profileService) {
        this.profileService = profileService;
    }

    @GetMapping("/api/v1/profile/{userId}")
    public ResponseEntity<?> getProfile(@PathVariable String userId) {
        return profileService.getProfile(userId)
            .<ResponseEntity<?>>map(ResponseEntity::ok)
            .orElse(ResponseEntity.notFound().build());
    }

    @PutMapping("/api/v1/profile/{userId}")
    public ResponseEntity<ProfileEntity> upsertProfile(@PathVariable String userId,
                                                        @RequestBody ProfileUpdateRequest request) {
        return ResponseEntity.ok(profileService.upsertProfile(userId, request));
    }

    @PostMapping("/api/v1/callback/profile")
    public ResponseEntity<Map<String, Object>> callbackProfile(@RequestBody Map<String, Object> body) {
        String userId = (String) body.get("user_id");
        @SuppressWarnings("unchecked")
        Map<String, Object> updates = (Map<String, Object>) body.get("updates");
        profileService.updateFromCallback(userId, updates);
        return ResponseEntity.ok(Map.of("success", true, "profile_id", userId));
    }

    @GetMapping("/api/v1/profile/{userId}/history")
    public ResponseEntity<Map<String, Object>> getProfileHistory(@PathVariable String userId) {
        return ResponseEntity.ok(Map.of("user_id", userId, "history", java.util.List.of()));
    }
}
