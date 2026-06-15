package com.shardflow.common.dto;

import java.time.Instant;
import java.util.List;
import java.util.Map;

/**
 * 用户画像 DTO
 * 关联规格: 记忆架构需求规格文档 6.4节、7.9节
 */
public final class UserProfileDTO {

    private UserProfileDTO() {}

    /** 画像更新请求 (PUT /api/v1/profile/{userId}) */
    public record UpdateRequest(
        PreferenceInput preference,
        InteractionHabitsInput interactionHabits
    ) {}

    /** 画像响应 (200 OK) */
    public record Response(
        Long profileId,
        String userId,
        PreferenceOutput preference,
        InteractionHabitsOutput interactionHabits,
        Integer profileVersion,
        Instant updatedAt
    ) {}

    /** 更新响应 (200 OK) */
    public record UpdateResponse(
        Long profileId,
        String status,
        Integer profileVersion
    ) {}

    /** 偏好输入 */
    public record PreferenceInput(
        List<String> interests,
        String expertise,
        String communicationStyle,
        Map<String, java.math.BigDecimal> preferredSources,
        String timezone
    ) {}

    /** 偏好输出 */
    public record PreferenceOutput(
        List<String> interests,
        String expertise,
        String communicationStyle,
        Map<String, java.math.BigDecimal> preferredSources,
        String timezone
    ) {}

    /** 交互习惯输入 */
    public record InteractionHabitsInput(
        List<String> commonTasks,
        String preferredDepth,
        String feedbackPatterns
    ) {}

    /** 交互习惯输出 */
    public record InteractionHabitsOutput(
        List<String> commonTasks,
        String preferredDepth,
        String feedbackPatterns
    ) {}
}
