package com.shardflow.common.entity;

import com.baomidou.mybatisplus.annotation.*;
import lombok.Data;
import lombok.NoArgsConstructor;
import java.time.Instant;

@Data
@NoArgsConstructor
@TableName("shardflow_audit_log")
public class AuditLogEntity {

    @TableId(type = IdType.AUTO)
    private Long id;

    @TableField("user_id")
    private String userId;

    @TableField("tool_name")
    private String toolName;

    @TableField("params_summary")
    private String paramsSummary;

    @TableField("success")
    private boolean success;

    @TableField("error")
    private String error;

    @TableField("latency_ms")
    private long latencyMs;

    @TableField(value = "created_at", fill = FieldFill.INSERT)
    private Instant createdAt;
}
