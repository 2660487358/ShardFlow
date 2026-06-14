package com.shardflow.memory.service;

import java.util.Map;

/**
 * Audit log service interface.
 * Provides audit log query and cleanup operations.
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
}
