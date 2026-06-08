package com.shardflow.common.entity;

import com.baomidou.mybatisplus.annotation.*;
import com.fasterxml.jackson.annotation.JsonProperty;
import lombok.Data;
import lombok.NoArgsConstructor;
import java.time.Instant;

@Data
@NoArgsConstructor
@TableName("shardflow_agent_config")
public class AgentConfigEntity {

    @TableId(type = IdType.AUTO)
    @JsonProperty(access = JsonProperty.Access.READ_ONLY)
    private Long id;

    @TableField("agent_code")
    @JsonProperty("agent_code")
    private String agentCode;

    @TableField("user_id")
    @JsonProperty("user_id")
    private String userId;

    @TableField("model_id")
    @JsonProperty("model_id")
    private String modelId;

    @TableField("name")
    private String name;

    @TableField("description")
    private String description;

    @TableField("system_prompt")
    @JsonProperty("system_prompt")
    private String systemPrompt;

    @TableField("temperature")
    private Double temperature;

    @TableField("max_tokens")
    @JsonProperty("max_tokens")
    private Integer maxTokens;

    @TableField("tools")
    private String tools;

    @TableField(value = "created_at", fill = FieldFill.INSERT)
    @JsonProperty("created_at")
    private Instant createdAt;

    @TableField(value = "updated_at", fill = FieldFill.INSERT_UPDATE)
    @JsonProperty("updated_at")
    private Instant updatedAt;
}
