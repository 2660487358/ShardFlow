package com.shardflow.mcp.service;

import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import com.baomidou.mybatisplus.extension.plugins.pagination.Page;
import com.shardflow.common.dto.mcp.McpAuditCallbackRequest;
import com.shardflow.common.dto.mcp.MetadataAuditLogResponse;
import com.shardflow.common.dto.mcp.ToolCallAuditLogResponse;
import com.shardflow.common.entity.McpMetadataAuditLogEntity;
import com.shardflow.common.entity.McpToolAuditLogEntity;
import com.shardflow.common.util.DataMasker;
import com.shardflow.mcp.repository.McpAuditLogRepository;
import com.shardflow.mcp.repository.McpMetadataAuditLogRepository;
import com.shardflow.usercontext.context.UserContext;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.dao.DuplicateKeyException;
import org.springframework.stereotype.Service;

import java.time.Instant;
import java.util.List;

/**
 * MCP 审计日志服务.
 *
 * <p>P3 阶段：Python 推理层回调记录工具调用审计日志 (FR-INVOKE-005, SEC-AUDIT-002).
 * <p>P5 阶段：工具元数据变更审计日志 (SEC-AUDIT-001, SEC-AUDIT-003).
 *
 * <p>审计日志仅追加写入 (SEC-AUDIT-004)，不支持修改或删除。
 */
@Slf4j
@Service
@RequiredArgsConstructor
public class McpAuditService {

    private final McpAuditLogRepository auditLogRepository;
    private final McpMetadataAuditLogRepository metadataAuditLogRepository;

    // ======================== P3: 工具调用审计 (SEC-AUDIT-002) ========================

    /**
     * 记录 MCP 工具调用审计日志.
     * 使用幂等键 (idempotencyKey) 防止重复写入.
     *
     * @param request 审计回调请求
     */
    public void recordAuditLog(McpAuditCallbackRequest request) {
        // 幂等性检查：通过 trace_id + span_id 判断是否已记录
        if (isDuplicate(request.getIdempotencyKey())) {
            log.debug("Duplicate audit log ignored: idempotencyKey={}", request.getIdempotencyKey());
            return;
        }

        McpToolAuditLogEntity entity = new McpToolAuditLogEntity();
        entity.setTraceId(request.getTraceId());
        entity.setSpanId(request.getSpanId());
        entity.setUserId(request.getUserId());
        entity.setSessionId(request.getSessionId());
        entity.setToolId(request.getToolId());
        entity.setToolName(request.getToolName());
        entity.setToolVersion(request.getToolVersion());
        // SEC-DATA-001: 审计日志输入参数和输出预览脱敏
        entity.setInputParams(DataMasker.maskAuditInput(request.getInputParams()));
        entity.setOutputPreview(DataMasker.maskAuditOutput(request.getOutputPreview()));
        entity.setStatus(request.getStatus());
        entity.setErrorCode(request.getErrorCode());
        entity.setErrorMsg(request.getErrorMsg());
        entity.setLatencyMs(request.getLatencyMs());
        entity.setRequestAt(request.getRequestAt());

        try {
            auditLogRepository.insert(entity);
        } catch (DuplicateKeyException e) {
            // SEC-AUDIT-002: 唯一索引 (trace_id, span_id) 防止并发重复插入
            log.info("Audit log already exists for trace_id={}, span_id={}", request.getTraceId(), request.getSpanId());
            return;
        }

        log.info("MCP audit log recorded: tool={}, status={}, latency={}ms, traceId={}",
            request.getToolName(), request.getStatus(),
            request.getLatencyMs(), request.getTraceId());
    }

    // ======================== P5: 元数据变更审计 (SEC-AUDIT-001, SEC-AUDIT-003) ========================

    /**
     * 记录工具注册审计日志 (SEC-AUDIT-001).
     */
    public void recordRegisterAudit(String userId, String toolId, String toolName, String afterSnapshot) {
        recordMetadataAudit(userId, toolId, toolName, "REGISTER",
            "Registered tool: " + toolName, null, afterSnapshot);
    }

    /**
     * 记录工具更新审计日志 (SEC-AUDIT-001).
     */
    public void recordUpdateAudit(String userId, String toolId, String toolName,
                                   String beforeSnapshot, String afterSnapshot) {
        recordMetadataAudit(userId, toolId, toolName, "UPDATE",
            "Updated tool: " + toolName, beforeSnapshot, afterSnapshot);
    }

    /**
     * 记录工具删除审计日志 (SEC-AUDIT-001).
     */
    public void recordDeleteAudit(String userId, String toolId, String toolName, String beforeSnapshot) {
        recordMetadataAudit(userId, toolId, toolName, "DELETE",
            "Deleted tool: " + toolName, beforeSnapshot, null);
    }

    /**
     * 记录工具状态变更审计日志 (SEC-AUDIT-001).
     */
    public void recordStatusChangeAudit(String userId, String toolId, String toolName,
                                         String fromStatus, String toStatus) {
        recordMetadataAudit(userId, toolId, toolName, "STATUS_CHANGE",
            "Status changed: " + fromStatus + " -> " + toStatus, null, null);
    }

    /**
     * 记录版本回退审计日志 (SEC-AUDIT-001).
     */
    public void recordRollbackAudit(String userId, String toolId, String toolName, String targetVersion) {
        recordMetadataAudit(userId, toolId, toolName, "ROLLBACK",
            "Rolled back to version: " + targetVersion, null, null);
    }

    /**
     * 通用元数据变更审计日志记录 (SEC-AUDIT-001, SEC-AUDIT-003).
     *
     * <p>审计日志包含完整字段：操作人、操作时间、操作类型、操作对象、变更内容。
     * 审计日志仅追加写入 (SEC-AUDIT-004)。
     */
    private void recordMetadataAudit(String userId, String toolId, String toolName,
                                      String operationType, String changeSummary,
                                      String beforeSnapshot, String afterSnapshot) {
        McpMetadataAuditLogEntity entity = new McpMetadataAuditLogEntity();
        entity.setUserId(userId);
        entity.setOperator(UserContext.getUserId() != null ? UserContext.getUserId() : userId);
        entity.setToolId(toolId);
        entity.setToolName(toolName);
        entity.setOperationType(operationType);
        entity.setChangeSummary(changeSummary);
        // SEC-DATA-001: 快照脱敏
        entity.setBeforeSnapshot(beforeSnapshot != null ? DataMasker.maskAuditInput(beforeSnapshot) : null);
        entity.setAfterSnapshot(afterSnapshot != null ? DataMasker.maskAuditInput(afterSnapshot) : null);
        entity.setOperationAt(Instant.now());

        metadataAuditLogRepository.insert(entity);

        log.info("MCP metadata audit: operation={}, tool={}, user={}, summary={}",
            operationType, toolName, userId, changeSummary);
    }

    // ======================== P5: 审计日志查询 ========================

    /**
     * 查询元数据变更审计日志 (SEC-AUDIT-001).
     * 用户隔离：仅查询当前用户的审计日志.
     *
     * @param toolId        工具ID（可选过滤条件）
     * @param operationType 操作类型（可选过滤条件）
     * @param page          页码（从1开始）
     * @param size          每页大小
     * @return 分页审计日志响应
     */
    public MetadataAuditLogResponse queryMetadataAuditLogs(String toolId, String operationType, int page, int size) {
        String userId = UserContext.getUserId();

        LambdaQueryWrapper<McpMetadataAuditLogEntity> wrapper = new LambdaQueryWrapper<McpMetadataAuditLogEntity>()
                .eq(McpMetadataAuditLogEntity::getUserId, userId)
                .orderByDesc(McpMetadataAuditLogEntity::getOperationAt);

        if (toolId != null && !toolId.isBlank()) {
            wrapper.eq(McpMetadataAuditLogEntity::getToolId, toolId);
        }
        if (operationType != null && !operationType.isBlank()) {
            wrapper.eq(McpMetadataAuditLogEntity::getOperationType, operationType);
        }

        Page<McpMetadataAuditLogEntity> pageResult = metadataAuditLogRepository.selectPage(new Page<>(page, size), wrapper);

        MetadataAuditLogResponse response = new MetadataAuditLogResponse();
        response.setTotal(pageResult.getTotal());
        response.setPage(page);
        response.setSize(size);

        List<MetadataAuditLogResponse.MetadataAuditEntry> entries = pageResult.getRecords().stream().map(entity -> {
            MetadataAuditLogResponse.MetadataAuditEntry entry = new MetadataAuditLogResponse.MetadataAuditEntry();
            entry.setId(entity.getId());
            entry.setUserId(entity.getUserId());
            entry.setOperator(entity.getOperator());
            entry.setToolId(entity.getToolId());
            entry.setToolName(entity.getToolName());
            entry.setOperationType(entity.getOperationType());
            entry.setChangeSummary(entity.getChangeSummary());
            entry.setOperationAt(entity.getOperationAt());
            return entry;
        }).toList();

        response.setLogs(entries);
        return response;
    }

    /**
     * 查询工具调用审计日志 (SEC-AUDIT-002).
     * 用户隔离：仅查询当前用户的审计日志.
     *
     * @param toolId 工具ID（可选过滤条件）
     * @param status 调用状态（可选过滤条件）
     * @param page   页码（从1开始）
     * @param size   每页大小
     * @return 分页审计日志响应
     */
    public ToolCallAuditLogResponse queryCallAuditLogs(String toolId, String status, int page, int size) {
        String userId = UserContext.getUserId();

        LambdaQueryWrapper<McpToolAuditLogEntity> wrapper = new LambdaQueryWrapper<McpToolAuditLogEntity>()
                .eq(McpToolAuditLogEntity::getUserId, userId)
                .orderByDesc(McpToolAuditLogEntity::getRequestAt);

        if (toolId != null && !toolId.isBlank()) {
            wrapper.eq(McpToolAuditLogEntity::getToolId, toolId);
        }
        if (status != null && !status.isBlank()) {
            wrapper.eq(McpToolAuditLogEntity::getStatus, status);
        }

        Page<McpToolAuditLogEntity> pageResult = auditLogRepository.selectPage(new Page<>(page, size), wrapper);

        ToolCallAuditLogResponse response = new ToolCallAuditLogResponse();
        response.setTotal(pageResult.getTotal());
        response.setPage(page);
        response.setSize(size);

        List<ToolCallAuditLogResponse.CallAuditEntry> entries = pageResult.getRecords().stream().map(entity -> {
            ToolCallAuditLogResponse.CallAuditEntry entry = new ToolCallAuditLogResponse.CallAuditEntry();
            entry.setId(entity.getId());
            entry.setTraceId(entity.getTraceId());
            entry.setSpanId(entity.getSpanId());
            entry.setUserId(entity.getUserId());
            entry.setSessionId(entity.getSessionId());
            entry.setToolId(entity.getToolId());
            entry.setToolName(entity.getToolName());
            entry.setToolVersion(entity.getToolVersion());
            entry.setInputParams(entity.getInputParams());
            entry.setOutputPreview(entity.getOutputPreview());
            entry.setStatus(entity.getStatus());
            entry.setErrorCode(entity.getErrorCode());
            entry.setErrorMsg(entity.getErrorMsg());
            entry.setLatencyMs(entity.getLatencyMs());
            entry.setRequestAt(entity.getRequestAt());
            return entry;
        }).toList();

        response.setLogs(entries);
        return response;
    }

    /**
     * 幂等性检查：通过 trace_id + span_id 组合判断是否已存在.
     */
    private boolean isDuplicate(String idempotencyKey) {
        if (idempotencyKey == null || idempotencyKey.isBlank()) {
            return false;
        }
        String[] parts = idempotencyKey.split("-", 2);
        if (parts.length < 2) {
            return false;
        }
        Long count = auditLogRepository.selectCount(
            new LambdaQueryWrapper<McpToolAuditLogEntity>()
                .eq(McpToolAuditLogEntity::getTraceId, parts[0])
                .eq(McpToolAuditLogEntity::getSpanId, parts[1])
        );
        return count != null && count > 0;
    }
}
