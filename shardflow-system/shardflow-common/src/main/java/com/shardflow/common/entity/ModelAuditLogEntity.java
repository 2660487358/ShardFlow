package com.shardflow.common.entity;

import com.baomidou.mybatisplus.annotation.*;
import com.fasterxml.jackson.annotation.JsonProperty;
import lombok.Data;
import lombok.NoArgsConstructor;
import java.time.Instant;

@Data
@NoArgsConstructor
@TableName("shardflow_model_audit_log")
public class ModelAuditLogEntity {

    @TableId(type = IdType.AUTO)
    private Long id;

    @TableField("user_id")
    @JsonProperty("user_id")
    private String userId;

    @TableField("action")
    private String action;

    @TableField("model_id")
    @JsonProperty("model_id")
    private String modelId;

    @TableField("model_type")
    @JsonProperty("model_type")
    private String modelType;

    @TableField("summary")
    private String summary;

    @TableField("success")
    private Boolean success;

    @TableField(value = "created_at", fill = FieldFill.INSERT)
    @JsonProperty("created_at")
    private Instant createdAt;
}
