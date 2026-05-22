package com.shardflow.common.dto;

import jakarta.validation.constraints.NotBlank;
import java.util.Map;

public record ShardSaveRequest(
    @NotBlank String taskId,
    @NotBlank String tenantId,
    int sessionSeq,
    Object confirmed,
    Object excluded,
    Object pending,
    Map<String, Double> sourcePreference,
    String explorationDepth,
    Object keyDecisions
) {}

public record ShardResponse(
    String id,
    String taskId,
    String tenantId,
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
