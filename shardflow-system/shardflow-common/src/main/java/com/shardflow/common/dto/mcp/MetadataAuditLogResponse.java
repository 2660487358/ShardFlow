package com.shardflow.common.dto.mcp;

import lombok.Data;

import java.time.Instant;
import java.util.List;

/**
 * MCP 工具元数据变更审计日志查询响应 DTO (SEC-AUDIT-001).
 */
@Data
public class MetadataAuditLogResponse {

    private List<MetadataAuditEntry> logs;
    private long total;
    private int page;
    private int size;

    @Data
    public static class MetadataAuditEntry {
        private Long id;
        private String userId;
        private String operator;
        private String toolId;
        private String toolName;
        private String operationType;
        private String changeSummary;
        private Instant operationAt;
    }
}
