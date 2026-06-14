package com.shardflow.common.dto.mcp;

import lombok.Data;
import lombok.NoArgsConstructor;

import java.time.Instant;

/**
 * 工具健康检查响应 DTO.
 * Per spec FR-HEALTH-001/FR-HEALTH-002: GET /api/v1/mcp/registry/tools/{toolId}/health
 */
@Data
@NoArgsConstructor
public class ToolHealthCheckResponse {

    private String toolId;

    private String toolName;

    /** HEALTHY / UNHEALTHY / UNKNOWN */
    private String healthStatus;

    private Instant lastHealthCheckAt;

    /** 连续失败次数 */
    private Integer consecutiveFailures;

    /** 连续成功次数 */
    private Integer consecutiveSuccesses;

    /** 检查结果消息 */
    private String message;

    /** 检查耗时（毫秒） */
    private Long latencyMs;
}
