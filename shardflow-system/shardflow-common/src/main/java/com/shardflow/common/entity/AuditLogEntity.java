package com.shardflow.common.entity;

import com.baomidou.mybatisplus.annotation.*;
import lombok.Data;
import lombok.NoArgsConstructor;
import java.time.Instant;

/**
 * 审计日志实体（C-4.9-01 增强版）。
 * <p>
 * 在原有 user_id/tool_name/params_summary/success/error/latency_ms/created_at 基础上，
 * 新增 trace_id/session_id/operation_type/resource_type/resource_id/ip_address 字段，
 * 满足 S4.9 审计日志写入要求：链路追踪、会话归属、操作分类、资源定位、来源审计。
 */
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

    // ===== S4.9 新增字段 =====

    /** 链路追踪ID，跨服务调用透传 */
    @TableField("trace_id")
    private String traceId;

    /** 会话ID，标识操作所属会话 */
    @TableField("session_id")
    private String sessionId;

    /** 操作类型：CREATE/UPDATE/DELETE/READ/EXECUTE/LOGIN/LOGOUT/AUTH */
    @TableField("operation_type")
    private String operationType;

    /** 资源类型：USER/SESSION/MEMORY/SHARD/PROFILE/STRATEGY/KB/MCP/TOOL */
    @TableField("resource_type")
    private String resourceType;

    /** 资源ID，标识具体被操作的资源实例 */
    @TableField("resource_id")
    private String resourceId;

    /** 来源IP地址，用于安全审计与异常溯源 */
    @TableField("ip_address")
    private String ipAddress;
}
