package com.shardflow.mcp.controller;

import com.shardflow.common.dto.Result;
import com.shardflow.common.dto.mcp.McpAuditCallbackRequest;
import com.shardflow.mcp.service.McpAuditService;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.validation.Valid;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.*;
import org.springframework.web.server.ResponseStatusException;

/**
 * MCP 审计回调 Controller.
 * 接收 Python 推理层的 MCP 工具调用审计日志回调 (IF-004, SEC-AUDIT-002).
 *
 * <p>基路径: /api/v1/callback/mcp
 * 认证: X-API-Key（服务间调用）
 */
@Slf4j
@RestController
@RequestMapping("/api/v1/callback/mcp")
@RequiredArgsConstructor
public class McpCallbackController {

    private final McpAuditService auditService;

    @Value("${shardflow.java-api-key:}")
    private String javaApiKey;

    /**
     * MCP 工具调用审计日志回调 (FR-INVOKE-005, SEC-AUDIT-002).
     * POST /api/v1/callback/mcp/audit
     */
    @PostMapping("/audit")
    public Result<Void> audit(@Valid @RequestBody McpAuditCallbackRequest request,
                              HttpServletRequest httpRequest) {
        checkApiKey(httpRequest);
        auditService.recordAuditLog(request);
        return Result.ok();
    }

    private void checkApiKey(HttpServletRequest request) {
        if (javaApiKey == null || javaApiKey.isBlank()) {
            log.error("java_api_key not configured, rejecting callback request");
            throw new ResponseStatusException(HttpStatus.UNAUTHORIZED, "API Key未配置，回调接口不可用");
        }
        String providedKey = request.getHeader("X-API-Key");
        if (providedKey == null || !javaApiKey.equals(providedKey)) {
            throw new ResponseStatusException(HttpStatus.UNAUTHORIZED, "Invalid or missing X-API-Key");
        }
    }
}
