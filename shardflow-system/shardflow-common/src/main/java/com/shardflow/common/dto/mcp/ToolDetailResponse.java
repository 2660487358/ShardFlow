package com.shardflow.common.dto.mcp;

import lombok.Data;
import lombok.NoArgsConstructor;

import java.time.Instant;
import java.util.List;
import java.util.Map;

/**
 * 工具详情响应 DTO.
 * Per spec section 5.1.3: GET /api/v1/mcp/registry/tools/{toolId}
 */
@Data
@NoArgsConstructor
public class ToolDetailResponse {

    private String toolId;

    private String toolName;

    private String toolType;

    private String description;

    private String category;

    private List<String> tags;

    private String mcpServerUrl;

    private String transport;

    private String healthCheckUrl;

    private Map<String, Object> inputSchema;

    private Map<String, Object> outputSchema;

    private List<String> permissions;

    private String riskLevel;

    private String version;

    private Integer timeoutSeconds;

    private Integer retryCount;

    private String authConfigType;

    private String status;

    private String healthStatus;

    private Instant lastHealthCheckAt;

    private String ownerTeam;

    private Map<String, Object> metadata;

    private Instant createdAt;

    private Instant updatedAt;

    private String createdBy;

    private String updatedBy;
}
