package com.shardflow.common.entity;

import com.baomidou.mybatisplus.annotation.*;
import lombok.Data;
import lombok.NoArgsConstructor;

import java.time.Instant;

@Data
@NoArgsConstructor
@TableName("mcp_tool_version")
public class McpToolVersionEntity {

    @TableId(type = IdType.AUTO)
    private Long id;

    @TableField("user_id")
    private String userId;

    @TableField("tool_id")
    private String toolId;

    @TableField("version")
    private String version;

    // 版本内容
    @TableField("input_schema")
    private String inputSchema;

    @TableField("output_schema")
    private String outputSchema;

    @TableField("description")
    private String description;

    @TableField("changelog")
    private String changelog;

    // 版本状态
    @TableField("status")
    private String status = "active";

    @TableField(value = "created_at", fill = FieldFill.INSERT)
    private Instant createdAt;

    @TableField("created_by")
    private String createdBy;
}
