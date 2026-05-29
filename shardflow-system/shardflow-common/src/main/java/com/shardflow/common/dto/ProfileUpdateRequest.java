package com.shardflow.common.dto;

public record ProfileUpdateRequest(
    Object preferences,
    Object expertise,
    Object habits
) {}
