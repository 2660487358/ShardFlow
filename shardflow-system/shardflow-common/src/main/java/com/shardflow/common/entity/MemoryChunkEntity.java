package com.shardflow.common.entity;

import com.baomidou.mybatisplus.annotation.*;
import lombok.Data;
import lombok.NoArgsConstructor;

import java.math.BigDecimal;
import java.time.Instant;

@Data
@NoArgsConstructor
@TableName("memory_chunks")
public class MemoryChunkEntity {

    @TableId(type = IdType.INPUT)
    private String chunkId;

    @TableField("user_id")
    private String userId;

    @TableField("memory_type")
    private String memoryType;

    @TableField("category")
    private String category;

    @TableField("content_text")
    private String contentText;

    @TableField("content_structured")
    private String contentStructured;

    @TableField("confidence")
    private BigDecimal confidence;

    @TableField("source")
    private String source;

    @TableField("source_session_id")
    private String sourceSessionId;

    @TableField("metadata")
    private String metadata;

    @TableField("has_conflict")
    private Boolean hasConflict;

    @TableField("conflict_with")
    private String conflictWith;

    @TableField("resolution_status")
    private String resolutionStatus;

    @TableField("is_deleted")
    private Boolean isDeleted;

    @TableField(value = "created_at", fill = FieldFill.INSERT)
    private Instant createdAt;

    @TableField(value = "updated_at", fill = FieldFill.INSERT_UPDATE)
    private Instant updatedAt;

    @TableField("expires_at")
    private Instant expiresAt;
}
