package com.shardflow.common.entity;

import com.baomidou.mybatisplus.annotation.*;
import com.baomidou.mybatisplus.extension.handlers.JacksonTypeHandler;
import com.fasterxml.jackson.annotation.JsonProperty;
import lombok.Data;
import lombok.NoArgsConstructor;
import java.time.Instant;
import java.util.List;

@Data
@NoArgsConstructor
@TableName(value = "shardflow_custom_model", autoResultMap = true)
public class CustomModelEntity {

    @TableId(type = IdType.AUTO)
    @JsonProperty(access = JsonProperty.Access.READ_ONLY)
    private Long id;

    @TableField("model_code")
    @JsonProperty("model_code")
    private String modelCode;

    @TableField("user_id")
    @JsonProperty("user_id")
    private String userId;

    @TableField("name")
    private String name;

    @TableField("provider")
    private String provider;

    @TableField("base_url")
    @JsonProperty("base_url")
    private String baseUrl;

    @TableField("model")
    private String model;

    @TableField("api_key_id")
    @JsonProperty("api_key_id")
    private String apiKeyId;

    @TableField("api_key_encrypted")
    @JsonProperty("api_key_encrypted")
    private String apiKeyEncrypted;

    @TableField(value = "capabilities", typeHandler = JacksonTypeHandler.class)
    private List<String> capabilities;

    @TableField("context_window")
    @JsonProperty("context_window")
    private Integer contextWindow;

    @TableField("enabled")
    private Boolean enabled;

    @TableField("is_verified")
    @JsonProperty("is_verified")
    private Boolean isVerified;

    @TableField(value = "created_at", fill = FieldFill.INSERT)
    @JsonProperty("created_at")
    private Instant createdAt;
}
