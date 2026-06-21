package com.shardflow.common.dto;

import java.math.BigDecimal;
import java.time.Instant;
import java.util.Map;

/**
 * 记忆片段 DTO
 * 关联规格: 记忆架构需求规格文档 6.1节、7.1-7.5节
 */
public final class MemoryChunkDTO {

    private MemoryChunkDTO() {}

    /** 记忆写入请求 (POST /api/v1/memory) */
    public record CreateRequest(
        String userId,
        String memoryType,
        String category,
        ContentInput content,
        BigDecimal confidence,
        String source,
        String sessionId,
        Map<String, Object> metadata
    ) {}

    /** 记忆更新请求 (PUT /api/v1/memory/{memoryId}) */
    public record UpdateRequest(
        ContentInput content,
        BigDecimal confidence,
        String source
    ) {}

    /** 记忆检索请求 (POST /api/v1/memory/search) */
    public record SearchRequest(
        String userId,
        String query,
        String searchType,
        Integer topK,
        SearchFilters filters
    ) {}

    /** 检索过滤条件 */
    public record SearchFilters(
        java.util.List<String> memoryType,
        java.util.List<String> category,
        String createdAfter,
        BigDecimal minConfidence
    ) {}

    /** 记忆写入响应 (201 Created) */
    public record CreateResponse(
        String memoryId,
        String status,
        Boolean conflictDetected,
        Instant createdAt
    ) {}

    /** 记忆更新响应 (200 OK) */
    public record UpdateResponse(
        String memoryId,
        String status,
        Integer version,
        Instant updatedAt
    ) {}

    /** 记忆读取响应 (200 OK) */
    public record DetailResponse(
        String memoryId,
        String userId,
        String memoryType,
        String category,
        ContentOutput content,
        MetadataOutput metadata,
        ConflictInfo conflictInfo
    ) {}

    /** 检索结果项 */
    public record SearchResultItem(
        String memoryId,
        String content,
        BigDecimal similarityScore,
        BigDecimal confidence,
        String category,
        Map<String, Object> metadata
    ) {}

    /** 检索响应 (200 OK) */
    public record SearchResponse(
        java.util.List<SearchResultItem> results,
        Integer total,
        Long searchTimeMs
    ) {}

    /** 内容输入 */
    public record ContentInput(
        String text,
        Map<String, Object> structured
    ) {}

    /** 内容输出 */
    public record ContentOutput(
        String text,
        Map<String, Object> structured,
        java.util.List<Float> embedding
    ) {}

    /** 元数据输出 */
    public record MetadataOutput(
        String source,
        String sessionId,
        BigDecimal confidence,
        Instant createdAt,
        Instant updatedAt,
        Instant expiresAt,
        Integer version,
        Integer accessCount,
        Instant lastAccessedAt
    ) {}

    /** 冲突信息 */
    public record ConflictInfo(
        Boolean hasConflict,
        String conflictWith,
        String resolutionStatus
    ) {}
}
