package com.shardflow.common.entity;

import com.baomidou.mybatisplus.annotation.*;
import lombok.Data;
import lombok.NoArgsConstructor;

import java.time.Instant;

@Data
@NoArgsConstructor
@TableName("session_state_summaries")
public class SessionStateSummaryEntity {

    @TableId(type = IdType.INPUT)
    private String summaryId;

    @TableField("user_id")
    private String userId;

    @TableField("task_id")
    private String taskId;

    @TableField("session_seq")
    private Integer sessionSeq;

    @TableField("task_type")
    private String taskType;

    @TableField("task_goal")
    private String taskGoal;

    @TableField("knowledge_state")
    private String knowledgeState;

    @TableField("user_context")
    private String userContext;

    @TableField("execution_state")
    private String executionState;

    @TableField("source_preference")
    private String sourcePreference;

    @TableField("version")
    private Integer version;

    @TableField("is_deleted")
    private Boolean isDeleted;

    @TableField(value = "created_at", fill = FieldFill.INSERT)
    private Instant createdAt;

    @TableField(value = "updated_at", fill = FieldFill.INSERT_UPDATE)
    private Instant updatedAt;
}
