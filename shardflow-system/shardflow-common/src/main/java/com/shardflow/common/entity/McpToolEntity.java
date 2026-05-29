package com.shardflow.common.entity;

import com.baomidou.mybatisplus.annotation.*;
import lombok.Data;
import lombok.NoArgsConstructor;
import java.time.Instant;

@Data
@NoArgsConstructor
@TableName("shardflow_mcp_tool")
public class McpToolEntity {

    @TableId(value = "tool_id", type = IdType.INPUT)
    private String toolId;

    @TableField("tool_name")
    private String toolName;

    @TableField("description")
    private String description;

    @TableField("mcp_server_url")
    private String mcpServerUrl;

    @TableField("input_schema")
    private String inputSchema;

    @TableField("output_schema")
    private String outputSchema;

    @TableField("permissions")
    private String permissions;

    @TableField("version")
    private String version;

    @TableField("status")
    private String status = "ACTIVE";

    @TableField("last_health_check")
    private Instant lastHealthCheck;
}
