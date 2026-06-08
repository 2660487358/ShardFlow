package com.shardflow.common.entity;

import com.baomidou.mybatisplus.annotation.*;
import lombok.Data;
import lombok.NoArgsConstructor;
import java.time.Instant;

@Data
@NoArgsConstructor
@TableName("shardflow_shard")
public class ShardEntity {

    @TableId(type = IdType.AUTO)
    private Long id;

    @TableField("user_id")
    private String userId;

    @TableField("task_id")
    private String taskId;

    @TableField("session_seq")
    private int sessionSeq;

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

    @TableField("confirmed")
    private String confirmed;

    @TableField("excluded")
    private String excluded;

    @TableField("pending")
    private String pending;

    @TableField("source_preference")
    private String sourcePreference;

    @TableField("exploration_depth")
    private String explorationDepth;

    @TableField("key_decisions")
    private String keyDecisions;

    @Version
    @TableField("version")
    private int version;

    @TableField("status")
    private String status = "SHARDED";

    @TableField(value = "created_at", fill = FieldFill.INSERT)
    private Instant createdAt;

    @TableField(value = "updated_at", fill = FieldFill.INSERT_UPDATE)
    private Instant updatedAt;
}
