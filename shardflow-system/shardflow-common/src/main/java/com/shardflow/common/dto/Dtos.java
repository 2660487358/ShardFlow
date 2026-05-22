package com.shardflow.common.dto;

import jakarta.validation.constraints.NotBlank;
import java.util.Map;

public record ShardSaveRequest(
    @NotBlank String taskId,
    @NotBlank String userId,
    int sessionSeq,
    String taskType,
    String taskGoal,
    Object knowledgeState,
    Object userContext,
    Object executionState,
    Map<String, Double> sourcePreference,
    Object confirmed,
    Object excluded,
    Object pending,
    String explorationDepth,
    Object keyDecisions
) {}

public record ShardResponse(
    String id,
    String taskId,
    String userId,
    int sessionSeq,
    Object confirmed,
    Object excluded,
    Object pending,
    int version,
    String status
) {}

public record StrategySearchRequest(
    @NotBlank String taskType,
    String query,
    double[] embedding,
    int limit
) {}

public record ApiError(int status, String message, String detail) {}

public record ProfileUpdateRequest(
    Object preferences,
    Object expertise,
    Object habits
) {}
