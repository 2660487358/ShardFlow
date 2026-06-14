package com.shardflow.common.dto.mcp;

import lombok.Data;
import lombok.NoArgsConstructor;

/**
 * 工具查询请求 DTO.
 * Per spec section 5.1.3: GET /api/v1/mcp/registry/tools
 */
@Data
@NoArgsConstructor
public class ToolQueryRequest {

    private String status;

    private String category;

    private String keyword;

    private Integer page = 1;

    private Integer size = 20;
}
