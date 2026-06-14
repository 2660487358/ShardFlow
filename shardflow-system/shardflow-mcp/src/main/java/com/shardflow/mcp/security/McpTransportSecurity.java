package com.shardflow.mcp.security;

import lombok.extern.slf4j.Slf4j;
import org.springframework.stereotype.Component;

/**
 * MCP 传输安全配置 (SEC-TRANS-001, SEC-TRANS-002, SEC-TRANS-003).
 *
 * <p>提供传输安全相关的校验和配置：
 * <ul>
 *   <li>SEC-TRANS-001: MCP Server 连接优先使用 HTTPS（TLS 1.2+）</li>
 *   <li>SEC-TRANS-002: Python 推理层与 Java 端回调通信限制在内网</li>
 *   <li>SEC-TRANS-003: MCP 注册中心接口仅通过 API 网关暴露</li>
 * </ul>
 */
@Slf4j
@Component
public class McpTransportSecurity {

    /**
     * 校验 MCP Server URL 是否使用 HTTPS (SEC-TRANS-001).
     * 如果 URL 使用 HTTP，记录警告日志但不阻止（兼容本地开发环境）。
     *
     * @param mcpServerUrl MCP Server URL
     * @return true 表示使用 HTTPS，false 表示使用 HTTP
     */
    public boolean validateHttpsPreferred(String mcpServerUrl) {
        if (mcpServerUrl == null || mcpServerUrl.isBlank()) {
            return false;
        }
        boolean isHttps = mcpServerUrl.toLowerCase().startsWith("https://");
        if (!isHttps) {
            // localhost 开发环境允许 HTTP
            boolean isLocalhost = mcpServerUrl.contains("localhost") || mcpServerUrl.contains("127.0.0.1");
            if (isLocalhost) {
                log.debug("MCP Server using HTTP for localhost (acceptable in dev): {}", mcpServerUrl);
            } else {
                log.warn("SEC-TRANS-001: MCP Server URL should use HTTPS (TLS 1.2+): {}", mcpServerUrl);
            }
        }
        return isHttps;
    }

    /**
     * 校验回调地址是否为内网地址 (SEC-TRANS-002).
     * Python 推理层与 Java 端之间的回调通信应限制在内网。
     *
     * @param callbackUrl 回调地址
     * @return true 表示为内网地址或 localhost
     */
    public boolean isInternalNetwork(String callbackUrl) {
        if (callbackUrl == null || callbackUrl.isBlank()) {
            return false;
        }
        String lower = callbackUrl.toLowerCase();
        return lower.contains("localhost")
            || lower.contains("127.0.0.1")
            || lower.contains("10.")
            || lower.contains("192.168.")
            || lower.matches(".*172\\.(1[6-9]|2[0-9]|3[01])\\..*");
    }

    /**
     * 校验后端服务不直接暴露公网 (SEC-TRANS-003).
     * MCP 注册中心接口应仅通过 API 网关暴露。
     * 此方法用于记录和验证配置。
     *
     * @param directAccessUrl 直接访问的 URL
     * @return true 表示通过网关访问，false 表示直接暴露
     */
    public boolean validateGatewayOnly(String directAccessUrl) {
        // 在实际部署中，这通过 Nginx/Kong 网关配置实现
        // 此处仅做日志记录和配置验证
        if (directAccessUrl != null && !directAccessUrl.isBlank()) {
            String lower = directAccessUrl.toLowerCase();
            boolean isInternal = isInternalNetwork(lower);
            if (!isInternal) {
                log.warn("SEC-TRANS-003: Backend service should not be directly exposed to public network: {}",
                    directAccessUrl);
            }
            return isInternal;
        }
        return true;
    }
}
