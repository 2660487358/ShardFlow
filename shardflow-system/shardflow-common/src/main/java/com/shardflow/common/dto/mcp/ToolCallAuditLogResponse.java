package com.shardflow.common.dto.mcp;

import lombok.Data;

import java.time.Instant;
import java.util.List;

/**
 * MCP 工具调用审计日志查询响应 DTO (SEC-AUDIT-002).
 */
@Data
public class ToolCallAuditLogResponse {

    private List<CallAuditEntry> logs;
    private long total;
    private int page;
    private int size;

    @Data
    public static class CallAuditEntry {
        private Long id;
        private String traceId;
        private String spanId;
        private String userId;
        private String sessionId;
        private String toolId;
        private String toolName;
        private String toolVersion;
        private String inputParams;
        private String outputPreview;
        private String status;
        private String errorCode;
        private String errorMsg;
        private Integer latencyMs;
        private Instant requestAt;
    }
}
