package com.shardflow.common.dto.profile;

import lombok.Data;
import lombok.NoArgsConstructor;

import java.util.List;
import java.util.Map;

/**
 * Request DTO for updating user profile.
 * Per spec section 7.9: PUT /api/v1/profile/{userId}
 */
@Data
@NoArgsConstructor
public class UserProfileUpdateRequest {

    private ProfileData preference;

    private InteractionHabitsData interactionHabits;

    @Data
    @NoArgsConstructor
    public static class ProfileData {
        private List<String> interests;
        private String expertise;
        private String communicationStyle;
        private Map<String, Double> preferredSources;
        private String timezone;
    }

    @Data
    @NoArgsConstructor
    public static class InteractionHabitsData {
        private List<String> commonTasks;
        private String preferredDepth;
        private String feedbackPatterns;
    }
}
