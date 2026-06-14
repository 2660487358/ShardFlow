package com.shardflow.common.entity;

import com.baomidou.mybatisplus.annotation.*;
import lombok.Data;
import lombok.NoArgsConstructor;

import java.time.Instant;

@Data
@NoArgsConstructor
@TableName("mcp_tool")
public class McpToolEntity {

    @TableId(type = IdType.AUTO)
    private Long id;

    @TableField("user_id")
    private String userId;

    @TableField("tool_id")
    private String toolId;

    @TableField("tool_name")
    private String toolName;

    // 工具类型：BUILTIN（内置工具）/ MCP（外部 MCP Server 工具）
    @TableField("tool_type")
    private String toolType = "MCP";

    // 基本描述
    @TableField("description")
    private String description;

    @TableField("category")
    private String category = "other";

    @TableField("tags")
    private String tags;

    // MCP Server 连接信息
    @TableField("mcp_server_url")
    private String mcpServerUrl;

    @TableField("transport")
    private String transport = "http-sse";

    @TableField("health_check_url")
    private String healthCheckUrl;

    // Schema 定义
    @TableField("input_schema")
    private String inputSchema;

    @TableField("output_schema")
    private String outputSchema;

    // 权限与风险
    @TableField("permissions")
    private String permissions;

    @TableField("risk_level")
    private String riskLevel = "low";

    // 版本控制
    @TableField("version")
    private String version = "1.0.0";

    // 调用配置
    @TableField("timeout_seconds")
    private Integer timeoutSeconds = 30;

    @TableField("retry_count")
    private Integer retryCount = 1;

    // 认证配置（加密存储）
    @TableField("auth_config")
    private String authConfig;

    // 状态管理
    @TableField("status")
    private String status = "DRAFT";

    @TableField("health_status")
    private String healthStatus = "UNKNOWN";

    @TableField("last_health_check_at")
    private Instant lastHealthCheckAt;

    // 归属信息
    @TableField("owner_team")
    private String ownerTeam = "personal";

    // 元数据
    @TableField("metadata")
    private String metadata;

    // 审计字段
    @TableField(value = "created_at", fill = FieldFill.INSERT)
    private Instant createdAt;

    @TableField(value = "updated_at", fill = FieldFill.INSERT_UPDATE)
    private Instant updatedAt;

    @TableField("created_by")
    private String createdBy;

    @TableField("updated_by")
    private String updatedBy;
}
