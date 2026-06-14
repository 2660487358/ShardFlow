package com.shardflow.common.dto.mcp;

import lombok.Data;
import lombok.NoArgsConstructor;

import java.time.Instant;
import java.util.List;

/**
 * 工具版本历史响应 DTO.
 * Per spec FR-VER-003: GET /api/v1/mcp/registry/tools/{toolId}/versions
 */
@Data
@NoArgsConstructor
public class ToolVersionResponse {

    private String toolId;

    private String toolName;

    private String currentVersion;

    private List<VersionEntry> versions;

    @Data
    @NoArgsConstructor
    public static class VersionEntry {

        private Long id;

        private String version;

        private String description;

        private String changelog;

        /** active / archived */
        private String status;

        private Instant createdAt;

        private String createdBy;
    }
}
