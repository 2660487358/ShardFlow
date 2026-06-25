package com.shardflow.common.dto.mcp;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Pattern;
import jakarta.validation.constraints.Size;
import lombok.Data;
import lombok.NoArgsConstructor;

import java.util.Map;

/**
 * 快速配置请求 DTO.
 * Per spec section 5.3.1: POST /api/v1/mcp/quick-setup
 */
@Data
@NoArgsConstructor
public class QuickConfigRequest {

    @NotBlank(message = "工具名称不能为空")
    @Size(max = 128, message = "工具名称最长128字符")
    private String name;

    @NotBlank(message = "显示名称不能为空")
    @Size(max = 256, message = "显示名称最长256字符")
    private String displayName;

    @NotBlank(message = "模板ID不能为空")
    @Size(max = 128, message = "模板ID最长128字符")
    private String template;

    @NotBlank(message = "传输类型不能为空")
    @Pattern(regexp = "stdio|sse|cloud", message = "传输类型必须为 stdio、sse 或 cloud")
    private String transport;

    @NotNull(message = "connection不能为空")
    private Map<String, Object> connection;

    private Map<String, String> env;

    private Integer timeoutSeconds;

    private Integer retryCount;
}
