package com.shardflow.memory.controller;

import com.shardflow.common.dto.Result;
import com.shardflow.memory.service.AuditService;
import jakarta.servlet.http.HttpServletRequest;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.*;
import org.springframework.web.server.ResponseStatusException;

import java.util.Map;

/**
 * REST API for audit log management.
 *
 * Endpoints:
 * - GET /api/v1/audit/logs — Query audit logs with filters (Appendix A)
 */
@Slf4j
@RestController
@RequestMapping("/api/v1/audit")
@RequiredArgsConstructor
public class AuditController {

    private final AuditService auditService;

    @Value("${shardflow.java-api-key:}")
    private String javaApiKey;

    private void checkApiKey(HttpServletRequest request) {
        if (javaApiKey == null || javaApiKey.isBlank()) {
            return; // Skip validation if not configured
        }
        String providedKey = request.getHeader("X-API-Key");
        if (providedKey == null || !javaApiKey.equals(providedKey)) {
            throw new ResponseStatusException(HttpStatus.UNAUTHORIZED, "Invalid or missing X-API-Key");
        }
    }

    /**
     * GET /api/v1/audit/logs — Query audit logs with filters.
     * Per spec Appendix A.
     */
    @GetMapping("/logs")
    public Result<Map<String, Object>> queryLogs(
            @RequestParam(value = "user_id", required = false) String userId,
            @RequestParam(value = "operation", required = false) String operation,
            @RequestParam(value = "start_time", required = false) String startTime,
            @RequestParam(value = "end_time", required = false) String endTime,
            @RequestParam(value = "page", defaultValue = "1") int page,
            @RequestParam(value = "page_size", defaultValue = "20") int pageSize,
            HttpServletRequest httpRequest) {
        checkApiKey(httpRequest);
        return Result.ok(auditService.queryAuditLogs(userId, operation, startTime, endTime, page, pageSize));
    }
}
