package com.shardflow.common.entity;

import com.baomidou.mybatisplus.annotation.*;
import lombok.Data;
import lombok.NoArgsConstructor;
import java.time.Instant;

@Data
@NoArgsConstructor
@TableName("shardflow_task_session")
public class TaskSessionEntity {

    @TableId(type = IdType.AUTO)
    private Long id;

    @TableField("task_id")
    private String taskId;

    @TableField("user_id")
    private String userId;

    @TableField("session_seq")
    private int sessionSeq;

    @TableField("source_port")
    private String sourcePort;

    @TableField("status")
    private String status = "ACTIVE";

    @TableField(value = "created_at", fill = FieldFill.INSERT)
    private Instant createdAt;
}
