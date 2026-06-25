package com.shardflow.common.dto.mcp;

import lombok.Data;
import lombok.NoArgsConstructor;

import java.time.Instant;
import java.util.Map;

/**
 * 快速配置响应 DTO.
 * Per spec section 5.3.2: Response 201 Created
 */
@Data
@NoArgsConstructor
public class QuickConfigResponse {

    private String toolId;

    private String toolName;

    private String template;

    private String status;

    private Instant createdAt;

    private Map<String, String> envMasked;
}
