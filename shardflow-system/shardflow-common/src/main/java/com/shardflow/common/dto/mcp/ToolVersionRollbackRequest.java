package com.shardflow.common.dto.mcp;

import lombok.Data;
import lombok.NoArgsConstructor;

/**
 * 版本回退请求 DTO.
 * Per spec FR-VER-004: PUT /api/v1/mcp/registry/tools/{toolId}/rollback
 */
@Data
@NoArgsConstructor
public class ToolVersionRollbackRequest {

    /** 目标版本号，为空则回退到上一个版本 */
    private String targetVersion;
}
