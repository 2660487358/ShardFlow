package com.shardflow.common.dto.mcp;

import lombok.Data;
import lombok.NoArgsConstructor;

import java.time.Instant;

/**
 * 审计日志回调请求 DTO.
 * Per spec section 5.4: POST /api/v1/callback/mcp/audit
 */
@Data
@NoArgsConstructor
public class McpAuditCallbackRequest {

    private String idempotencyKey;

    private String traceId;

    private String spanId;

    private String userId;

    private String agentId;

    private String sessionId;

    private String toolId;

    private String toolName;

    private String toolVersion;

    private String inputParams;

    private String outputPreview;

    private String status;

    private Integer latencyMs;

    private String errorCode;

    private String errorMsg;

    private Instant requestAt;
}
