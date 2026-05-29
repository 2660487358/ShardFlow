package com.shardflow.common.dto;

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
