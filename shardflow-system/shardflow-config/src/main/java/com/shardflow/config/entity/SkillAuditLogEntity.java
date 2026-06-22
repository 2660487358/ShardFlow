package com.shardflow.config.entity;

import com.baomidou.mybatisplus.annotation.*;
import com.fasterxml.jackson.annotation.JsonProperty;
import lombok.Data;
import lombok.NoArgsConstructor;

import java.time.Instant;

/**
 * Skill 审计日志实体，映射 skill_audit_log 表.
 *
 * <p>Per Skills管理需求规格文档 7.1.6 / DR-1 / FR-8.7 / FR-8.8.
 * <p>记录所有 Skill 操作与执行调用：CRUD/版本发布/权限变更/执行调用/导入导出。
 * operation 取值：CREATE | UPDATE | DELETE | STATUS_CHANGE | PUBLISH | ROLLBACK |
 *                 PERMISSION_CHANGE | EXECUTE | IMPORT | EXPORT | SKILL_LOAD。
 * <p>P6 阶段扩展字段：latency_ms / tokens_used / success / error / session_id，
 *                    支持成本归因与性能分析。
 */
@Data
@NoArgsConstructor
@TableName("skill_audit_log")
public class SkillAuditLogEntity {

    @TableId(type = IdType.AUTO)
    @JsonProperty(access = JsonProperty.Access.READ_ONLY)
    private Long id;

    /** Skill ID（可为空，如批量操作） */
    @TableField("skill_id")
    @JsonProperty("skill_id")
    private Long skillId;

    /** Agent 编码（执行调用时记录） */
    @TableField("agent_id")
    @JsonProperty("agent_id")
    private String agentId;

    /** 会话ID（执行调用时记录，用于关联对话上下文） */
    @TableField("session_id")
    @JsonProperty("session_id")
    private String sessionId;

    /** 操作类型 */
    @TableField("operation")
    private String operation;

    /** 操作者ID */
    @TableField("operator_id")
    @JsonProperty("operator_id")
    private String operatorId;

    /** 操作者类型：user | system | api */
    @TableField("operator_type")
    @JsonProperty("operator_type")
    private String operatorType = "user";

    /** 请求ID，用于链路追踪 */
    @TableField("request_id")
    @JsonProperty("request_id")
    private String requestId;

    /** 操作详情，JSONB格式 */
    @TableField("details")
    private String details;

    /** IP 地址 */
    @TableField("ip_address")
    @JsonProperty("ip_address")
    private String ipAddress;

    /** User-Agent */
    @TableField("user_agent")
    @JsonProperty("user_agent")
    private String userAgent;

    /** 调用延迟（毫秒），P6 新增 */
    @TableField("latency_ms")
    @JsonProperty("latency_ms")
    private Integer latencyMs = 0;

    /** Token 消耗（input + output），P6 新增 */
    @TableField("tokens_used")
    @JsonProperty("tokens_used")
    private Integer tokensUsed = 0;

    /** 执行是否成功，P6 新增 */
    @TableField("success")
    @JsonProperty("success")
    private Boolean success = true;

    /** 错误信息（失败时记录），P6 新增 */
    @TableField("error")
    @JsonProperty("error")
    private String error;

    @TableField(value = "created_at", fill = FieldFill.INSERT)
    @JsonProperty("created_at")
    private Instant createdAt;
}
