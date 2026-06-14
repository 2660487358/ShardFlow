package com.shardflow.common.dto.mcp;

import lombok.Data;
import lombok.NoArgsConstructor;

import java.time.Instant;
import java.util.List;

/**
 * 工具列表响应 DTO.
 * Per spec section 5.1.3: Response
 */
@Data
@NoArgsConstructor
public class ToolListResponse {

    private List<ToolSummary> tools;

    private Long total;

    private Integer page;

    private Integer size;

    @Data
    @NoArgsConstructor
    public static class ToolSummary {
        private String toolId;
        private String toolName;
        private String toolType;
        private String description;
        private String category;
        private List<String> tags;
        private String version;
        private String status;
        private String healthStatus;
        private List<String> permissions;
        private String mcpServerUrl;
        private String transport;
        private String riskLevel;
        private String ownerTeam;
        private Instant createdAt;
        private Instant updatedAt;
    }
}
