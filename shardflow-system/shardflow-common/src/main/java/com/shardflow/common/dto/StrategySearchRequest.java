package com.shardflow.common.dto;

import jakarta.validation.constraints.NotBlank;

public record StrategySearchRequest(
    @NotBlank String taskType,
    String query,
    double[] embedding,
    int limit
) {}
