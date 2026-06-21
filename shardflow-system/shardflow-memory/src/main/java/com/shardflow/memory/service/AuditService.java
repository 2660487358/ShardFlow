package com.shardflow.memory.service;

import com.shardflow.common.entity.AuditLogEntity;

import java.util.Map;

/**
 * Audit log service interface.
 * Provides audit log query, write, and cleanup operations.
 * <p>
 * 规则条款：C-4.9-01（审计日志写入）、C-4.9-02（敏感操作审计）、C-11.3（审计可追溯）。
 */
public interface AuditService {

    /**
     * Query audit logs with filters.
     */
    Map<String, Object> queryAuditLogs(String userId, String operation, String startTime, String endTime, int page, int pageSize);

    /**
     * Delete audit logs older than retention period.
     */
    int cleanupOldLogs(int retentionDays);

    /**
     * 记录审计日志（C-4.9-01）。
     * <p>
     * 用于敏感操作的统一审计入口，填充增强字段（trace_id/session_id/operation_type 等）。
     *
     * @param entity 预填充好的审计日志实体
     * @return 写入后的实体（含生成的 id）
     */
    AuditLogEntity recordAudit(AuditLogEntity entity);

    /**
     * 记录敏感操作审计（C-4.9-02 便捷方法）。
     *
     * @param userId        用户ID
     * @param sessionId     会话ID（可空）
     * @param traceId       链路追踪ID（可空）
     * @param operationType 操作类型（CREATE/UPDATE/DELETE/EXECUTE/AUTH 等）
     * @param resourceType  资源类型（USER/SESSION/MEMORY/PROFILE/STRATEGY/KB/MCP/TOOL）
     * @param resourceId    资源ID
     * @param toolName      工具名/接口名
     * @param paramsSummary 参数摘要（脱敏后）
     * @param success       是否成功
     * @param error         错误信息（失败时）
     * @param latencyMs     耗时（毫秒）
     * @param ipAddress     来源IP
     * @return 写入后的实体
     */
    default AuditLogEntity recordSensitiveOperation(
            String userId, String sessionId, String traceId,
            String operationType, String resourceType, String resourceId,
            String toolName, String paramsSummary,
            boolean success, String error, long latencyMs, String ipAddress) {
        AuditLogEntity entity = new AuditLogEntity();
        entity.setUserId(userId);
        entity.setSessionId(sessionId);
        entity.setTraceId(traceId);
        entity.setOperationType(operationType);
        entity.setResourceType(resourceType);
        entity.setResourceId(resourceId);
        entity.setToolName(toolName);
        entity.setParamsSummary(paramsSummary);
        entity.setSuccess(success);
        entity.setError(error);
        entity.setLatencyMs(latencyMs);
        entity.setIpAddress(ipAddress);
        return recordAudit(entity);
    }
}
