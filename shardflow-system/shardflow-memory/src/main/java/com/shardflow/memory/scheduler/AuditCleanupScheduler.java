package com.shardflow.memory.scheduler;

import com.shardflow.memory.service.AuditService;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;

/**
 * Scheduled task for cleaning up old audit logs.
 * Runs daily at 3 AM, deleting logs older than 180 days.
 */
@Slf4j
@Component
@RequiredArgsConstructor
public class AuditCleanupScheduler {

    private final AuditService auditService;

    private static final int DEFAULT_RETENTION_DAYS = 180;

    @Scheduled(cron = "0 0 3 * * ?")
    public void cleanupOldAuditLogs() {
        log.info("Starting audit log cleanup, retention days: {}", DEFAULT_RETENTION_DAYS);
        try {
            int deleted = auditService.cleanupOldLogs(DEFAULT_RETENTION_DAYS);
            log.info("Audit log cleanup completed: {} logs deleted", deleted);
        } catch (Exception e) {
            log.error("Audit log cleanup failed", e);
        }
    }
}
