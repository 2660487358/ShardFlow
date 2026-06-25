package com.shardflow.common.entity;

import com.baomidou.mybatisplus.annotation.*;
import lombok.Data;
import lombok.NoArgsConstructor;

import java.time.Instant;

/**
 * MCP 快速配置模板实体.
 * Per spec section 5.2: mcp_quick_template 表映射
 */
@Data
@NoArgsConstructor
@TableName("mcp_quick_template")
public class McpQuickTemplateEntity {

    @TableId(type = IdType.AUTO)
    private Long id;

    @TableField("template_id")
    private String templateId;

    @TableField("display_name")
    private String displayName;

    @TableField("category")
    private String category;

    @TableField("description")
    private String description;

    @TableField("icon_url")
    private String iconUrl;

    @TableField("transport")
    private String transport;

    @TableField("default_connection")
    private String defaultConnection;

    @TableField("input_schema")
    private String inputSchema;

    @TableField("output_schema")
    private String outputSchema;

    @TableField("default_env_vars")
    private String defaultEnvVars;

    @TableField("env_var_descriptions")
    private String envVarDescriptions;

    @TableField("auth_type")
    private String authType;

    @TableField("tags")
    private String tags;

    @TableField("sort_order")
    private Integer sortOrder;

    @TableField("status")
    private String status;

    @TableField(value = "created_at", fill = FieldFill.INSERT)
    private Instant createdAt;

    @TableField(value = "updated_at", fill = FieldFill.INSERT_UPDATE)
    private Instant updatedAt;
}
