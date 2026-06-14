package com.shardflow.common.dto.mcp;

import lombok.Data;
import lombok.NoArgsConstructor;

/**
 * 工具状态变更请求 DTO.
 * Per spec section 5.1.5: PUT /api/v1/mcp/registry/tools/{toolId}/status
 */
@Data
@NoArgsConstructor
public class ToolStatusChangeRequest {

    private String status;
}
