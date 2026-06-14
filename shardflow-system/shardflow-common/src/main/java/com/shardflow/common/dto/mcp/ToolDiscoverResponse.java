package com.shardflow.common.dto.mcp;

import lombok.Data;
import lombok.NoArgsConstructor;

import java.util.List;
import java.util.Map;

/**
 * 工具发现响应 DTO.
 * Per spec section 5.1.6: GET /api/v1/mcp/registry/tools/discover
 */
@Data
@NoArgsConstructor
public class ToolDiscoverResponse {

    private List<DiscoveredTool> tools;

    private String snapshotVersion;

    @Data
    @NoArgsConstructor
    public static class DiscoveredTool {
        private String toolId;
        private String toolName;
        private String toolType;
        private String description;
        private String category;
        private String version;
        private Map<String, Object> inputSchema;
        private Map<String, Object> outputSchema;
        private List<String> permissions;
        private String mcpServerUrl;
        private String transport;
        private Integer timeoutSeconds;
        private Integer retryCount;
        private String riskLevel;
    }
}
