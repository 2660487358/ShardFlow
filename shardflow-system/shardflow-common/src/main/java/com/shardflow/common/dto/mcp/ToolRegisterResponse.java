package com.shardflow.common.dto.mcp;

import lombok.Data;
import lombok.NoArgsConstructor;

import java.time.Instant;

/**
 * 工具注册响应 DTO.
 * Per spec section 5.1.4: Response 201 Created
 */
@Data
@NoArgsConstructor
public class ToolRegisterResponse {

    private String toolId;

    private String toolName;

    private String status;

    private String version;

    private Instant createdAt;
}
