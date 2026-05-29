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
