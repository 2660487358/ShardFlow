package com.shardflow.common.dto.mcp;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Pattern;
import jakarta.validation.constraints.Size;
import lombok.Data;
import lombok.NoArgsConstructor;

import java.util.List;
import java.util.Map;

/**
 * 工具注册请求 DTO.
 * Per spec section 5.1.4: POST /api/v1/mcp/registry/tools
 */
@Data
@NoArgsConstructor
public class ToolRegisterRequest {

    @NotBlank(message = "工具名称不能为空")
    @Size(max = 128, message = "工具名称最长128字符")
    private String toolName;

    private String description;

    private String category;

    private List<String> tags;

    @NotBlank(message = "MCP Server地址不能为空")
    @Size(max = 512, message = "MCP Server地址最长512字符")
    private String mcpServerUrl;

    private String transport;

    private String healthCheckUrl;

    @NotNull(message = "input_schema不能为空")
    private Map<String, Object> inputSchema;

    private Map<String, Object> outputSchema;

    private List<String> permissions;

    private String riskLevel;

    @NotBlank(message = "版本号不能为空")
    @Pattern(regexp = "\\d+\\.\\d+\\.\\d+", message = "版本号格式必须为MAJOR.MINOR.PATCH")
    private String version;

    private Integer timeoutSeconds;

    private Integer retryCount;

    private AuthConfig authConfig;

    private String ownerTeam;

    private Map<String, Object> metadata;

    @Data
    @NoArgsConstructor
    public static class AuthConfig {
        private String type;
        private String tokenKey;
        private String keyName;
        private String keyValueEnv;
        private String clientIdEnv;
        private String clientSecretEnv;
        private String tokenUrl;
    }
}
