package com.shardflow.mcp.audit;

import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import com.shardflow.common.entity.McpMetadataAuditLogEntity;
import com.shardflow.common.entity.McpToolAuditLogEntity;
import com.shardflow.mcp.repository.McpAuditLogRepository;
import com.shardflow.mcp.repository.McpMetadataAuditLogRepository;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;

import java.time.Instant;
import java.time.temporal.ChronoUnit;

/**
 * MCP 审计日志保留策略定时任务 (SEC-AUDIT-005).
 *
 * <p>保留期限 >= 90 天，每天凌晨 3:00 清理过期审计日志。
 * 仅删除过期记录，不修改或篡改未过期记录 (SEC-AUDIT-004).
 */
@Slf4j
@Component
@RequiredArgsConstructor
public class McpAuditRetentionScheduler {

    /** 审计日志保留天数 (SEC-AUDIT-005: >= 90 天) */
    private static final int RETENTION_DAYS = 90;

    private final McpAuditLogRepository auditLogRepository;
    private final McpMetadataAuditLogRepository metadataAuditLogRepository;

    /**
     * 每天凌晨 3:00 清理过期审计日志.
     */
    @Scheduled(cron = "0 0 3 * * ?")
    public void cleanupExpiredAuditLogs() {
        Instant cutoff = Instant.now().minus(RETENTION_DAYS, ChronoUnit.DAYS);

        // 清理工具调用审计日志
        int callLogsDeleted = cleanupCallAuditLogs(cutoff);
        // 清理元数据变更审计日志
        int metadataLogsDeleted = cleanupMetadataAuditLogs(cutoff);

        if (callLogsDeleted > 0 || metadataLogsDeleted > 0) {
            log.info("Audit log retention cleanup: deleted {} call logs and {} metadata logs older than {} days",
                callLogsDeleted, metadataLogsDeleted, RETENTION_DAYS);
        }
    }

    private int cleanupCallAuditLogs(Instant cutoff) {
        try {
            LambdaQueryWrapper<McpToolAuditLogEntity> wrapper = new LambdaQueryWrapper<McpToolAuditLogEntity>()
                .lt(McpToolAuditLogEntity::getRequestAt, cutoff);
            return auditLogRepository.delete(wrapper);
        } catch (Exception e) {
            log.error("Failed to cleanup expired call audit logs", e);
            return 0;
        }
    }

    private int cleanupMetadataAuditLogs(Instant cutoff) {
        try {
            LambdaQueryWrapper<McpMetadataAuditLogEntity> wrapper = new LambdaQueryWrapper<McpMetadataAuditLogEntity>()
                .lt(McpMetadataAuditLogEntity::getOperationAt, cutoff);
            return metadataAuditLogRepository.delete(wrapper);
        } catch (Exception e) {
            log.error("Failed to cleanup expired metadata audit logs", e);
            return 0;
        }
    }
}
