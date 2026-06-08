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
@TableName(value = "sf_model_builtin", autoResultMap = true)
public class BuiltinModelEntity {

    @TableId(type = IdType.AUTO)
    private Long id;

    @TableField("model_code")
    @JsonProperty("model_code")
    private String modelCode;

    @TableField("name")
    private String name;

    @TableField("provider")
    private String provider;

    @TableField("model")
    private String model;

    @TableField("base_url")
    @JsonProperty("base_url")
    private String baseUrl;

    @TableField("api_key_env")
    @JsonProperty("api_key_env")
    private String apiKeyEnv;

    @TableField(value = "capabilities", typeHandler = JacksonTypeHandler.class)
    private List<String> capabilities;

    @TableField("context_window")
    @JsonProperty("context_window")
    private Integer contextWindow;

    @TableField("is_enabled")
    @JsonProperty("is_enabled")
    private Boolean isEnabled;

    @TableField("sort_order")
    @JsonProperty("sort_order")
    private Integer sortOrder;

    @TableField(value = "created_at", fill = FieldFill.INSERT)
    @JsonProperty("created_at")
    private Instant createdAt;

    @TableField(value = "updated_at", fill = FieldFill.INSERT_UPDATE)
    @JsonProperty("updated_at")
    private Instant updatedAt;
}
