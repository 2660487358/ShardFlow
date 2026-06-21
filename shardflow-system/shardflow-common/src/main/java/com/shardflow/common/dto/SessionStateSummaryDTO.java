package com.shardflow.common.dto;

import java.math.BigDecimal;
import java.time.Instant;
import java.util.List;
import java.util.Map;

/**
 * 会话状态摘要 DTO
 * 关联规格: 记忆架构需求规格文档 6.2节、7.6-7.7节
 */
public final class SessionStateSummaryDTO {

    private SessionStateSummaryDTO() {}

    /** 快照保存请求 (POST /api/v1/session-summary) */
    public record CreateRequest(
        String userId,
        String taskId,
        Integer sessionSeq,
        String taskType,
        String taskGoal,
        String compressedHistory,
        KnowledgeState knowledgeState,
        UserContext userContext,
        ExecutionState executionState,
        Map<String, BigDecimal> sourcePreference
    ) {}

    /** 快照更新请求 (PUT /api/v1/session-summary/{summaryId}) */
    public record UpdateRequest(
        String compressedHistory,
        KnowledgeState knowledgeState,
        UserContext userContext,
        ExecutionState executionState,
        Map<String, BigDecimal> sourcePreference
    ) {}

    /** 快照响应 (200 OK / 201 Created) */
    public record Response(
        String summaryId,
        String userId,
        String taskId,
        Integer sessionSeq,
        String taskType,
        String taskGoal,
        String compressedHistory,
        KnowledgeState knowledgeState,
        UserContext userContext,
        ExecutionState executionState,
        Map<String, BigDecimal> sourcePreference,
        Integer version,
        Instant createdAt,
        Instant updatedAt
    ) {}

    /** 创建响应 (201 Created) */
    public record CreateResponse(
        String summaryId,
        String status,
        Instant createdAt
    ) {}

    /** 知识状态 */
    public record KnowledgeState(
        List<String> confirmed,
        List<String> excluded,
        List<String> pending,
        List<KeyDecision> keyDecisions
    ) {}

    /** 关键决策 */
    public record KeyDecision(
        String decision,
        String reason,
        java.math.BigDecimal confidence
    ) {}

    /** 用户上下文 */
    public record UserContext(
        String expertiseLevel,
        String preferredDepth,
        String communicationStyle
    ) {}

    /** 执行状态 */
    public record ExecutionState(
        Integer completedSteps,
        String currentStep,
        List<String> toolsUsed,
        String estimatedRemaining
    ) {}
}
