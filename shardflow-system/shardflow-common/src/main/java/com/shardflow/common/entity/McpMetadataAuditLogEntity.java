package com.shardflow.common.entity;

import com.baomidou.mybatisplus.annotation.*;
import lombok.Data;
import lombok.NoArgsConstructor;

import java.time.Instant;

/**
 * MCP 工具元数据变更审计日志实体.
 * 映射 mcp_metadata_audit_log 表 (SEC-AUDIT-001, SEC-AUDIT-003).
 *
 * <p>记录工具注册/更新/删除/状态变更等元数据操作审计日志，
 * 与 McpToolAuditLogEntity（工具调用审计）分离。
 */
@Data
@NoArgsConstructor
@TableName("mcp_metadata_audit_log")
public class McpMetadataAuditLogEntity {

    @TableId(type = IdType.AUTO)
    private Long id;

    /** 操作人用户ID */
    @TableField("user_id")
    private String userId;

    /** 操作人标识 */
    @TableField("operator")
    private String operator;

    /** 工具ID */
    @TableField("tool_id")
    private String toolId;

    /** 工具名称 */
    @TableField("tool_name")
    private String toolName;

    /** 操作类型: REGISTER/UPDATE/DELETE/STATUS_CHANGE/ROLLBACK */
    @TableField("operation_type")
    private String operationType;

    /** 变更摘要 */
    @TableField("change_summary")
    private String changeSummary;

    /** 变更前快照（脱敏） */
    @TableField("before_snapshot")
    private String beforeSnapshot;

    /** 变更后快照（脱敏） */
    @TableField("after_snapshot")
    private String afterSnapshot;

    /** 操作时间 */
    @TableField("operation_at")
    private Instant operationAt;
}
