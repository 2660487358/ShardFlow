package com.shardflow.common.entity;

import com.baomidou.mybatisplus.annotation.*;
import lombok.Data;
import lombok.NoArgsConstructor;
import java.time.Instant;

@Data
@NoArgsConstructor
@TableName("shardflow_task")
public class TaskEntity {

    @TableId(type = IdType.AUTO)
    private Long id;

    @TableField("task_code")
    private String taskCode;

    @TableField("user_id")
    private String userId;

    @TableField("title")
    private String title;

    @TableField("description")
    private String description;

    @TableField("status")
    private String status = "PENDING";

    @TableField("session_id")
    private String sessionId;

    @TableField(value = "created_at", fill = FieldFill.INSERT)
    private Instant createdAt;

    @TableField(value = "updated_at", fill = FieldFill.INSERT_UPDATE)
    private Instant updatedAt;
}
