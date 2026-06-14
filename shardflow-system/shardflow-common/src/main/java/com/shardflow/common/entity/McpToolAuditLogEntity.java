package com.shardflow.common.entity;

import com.baomidou.mybatisplus.annotation.*;
import lombok.Data;
import lombok.NoArgsConstructor;

import java.time.Instant;

@Data
@NoArgsConstructor
@TableName("mcp_tool_audit_log")
public class McpToolAuditLogEntity {

    @TableId(type = IdType.AUTO)
    private Long id;

    // 追踪信息
    @TableField("trace_id")
    private String traceId;

    @TableField("span_id")
    private String spanId;

    // 用户信息
    @TableField("user_id")
    private String userId;

    @TableField("session_id")
    private String sessionId;

    // 工具信息
    @TableField("tool_id")
    private String toolId;

    @TableField("tool_name")
    private String toolName;

    @TableField("tool_version")
    private String toolVersion;

    // 调用详情
    @TableField("input_params")
    private String inputParams;

    @TableField("output_preview")
    private String outputPreview;

    // 执行结果
    @TableField("status")
    private String status;

    @TableField("error_code")
    private String errorCode;

    @TableField("error_msg")
    private String errorMsg;

    // 性能指标
    @TableField("latency_ms")
    private Integer latencyMs;

    // 时间戳
    @TableField("request_at")
    private Instant requestAt;
}
