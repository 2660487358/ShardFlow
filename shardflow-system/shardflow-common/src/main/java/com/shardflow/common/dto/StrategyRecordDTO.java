package com.shardflow.common.dto;

import java.math.BigDecimal;
import java.time.Instant;
import java.util.List;
import java.util.Map;

/**
 * 策略记录 DTO
 * 关联规格: 记忆架构需求规格文档 6.3节、7.8节
 */
public final class StrategyRecordDTO {

    private StrategyRecordDTO() {}

    /** 策略检索请求 (POST /api/v1/strategy/search) */
    public record SearchRequest(
        String userId,
        String query,
        String taskType,
        Integer topK,
        BigDecimal minSimilarity
    ) {}

    /** 策略检索结果项 */
    public record SearchResultItem(
        String recordId,
        String taskType,
        String queryPattern,
        List<ToolComboItem> toolCombo,
        BigDecimal successScore,
        BigDecimal similarityScore
    ) {}

    /** 策略检索响应 (200 OK) */
    public record SearchResponse(
        List<SearchResultItem> results,
        Integer total,
        Long searchTimeMs
    ) {}

    /** 策略记录详情响应 */
    public record DetailResponse(
        String recordId,
        String userId,
        String taskType,
        String queryPattern,
        List<ToolComboItem> toolCombo,
        Map<String, String> userFeedback,
        BigDecimal successScore,
        Integer costMs,
        Instant createdAt
    ) {}

    /** 策略反馈请求 (POST /api/v1/strategy/{recordId}/feedback) */
    public record FeedbackRequest(
        Map<String, String> userFeedback,
        BigDecimal successScore
    ) {}

    /** 工具组合项 */
    public record ToolComboItem(
        String tool,
        BigDecimal weight,
        BigDecimal reliability
    ) {}
}
