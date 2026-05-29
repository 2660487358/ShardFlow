package com.shardflow.callback.controller;

import com.shardflow.callback.service.CallbackService;
import com.shardflow.callback.util.IdempotencyUtil;
import com.shardflow.common.dto.Result;
import com.shardflow.common.dto.ShardSaveRequest;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.validation.Valid;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.*;
import org.springframework.web.server.ResponseStatusException;

import java.util.Map;

@Slf4j
@RestController
@RequestMapping("/api/v1/callback")
@RequiredArgsConstructor
public class CallbackController {

    private final CallbackService callbackService;
    private final IdempotencyUtil idempotencyUtil;

    @Value("${shardflow.java-api-key:}")
    private String javaApiKey;

    private void checkApiKey(HttpServletRequest request) {
        if (javaApiKey == null || javaApiKey.isBlank()) {
            log.warn("java_api_key not configured, skipping API key validation");
            return;
        }
        String providedKey = request.getHeader("X-API-Key");
        if (providedKey == null || !javaApiKey.equals(providedKey)) {
            throw new ResponseStatusException(HttpStatus.UNAUTHORIZED, "Invalid or missing X-API-Key");
        }
    }

    @PostMapping("/shards")
    public Result<Map<String, Object>> saveShard(
            @Valid @RequestBody ShardSaveRequest request,
            HttpServletRequest httpRequest) {
        checkApiKey(httpRequest);
        String idempotencyKey = httpRequest.getHeader("X-Idempotency-Key");
        if (idempotencyKey != null && idempotencyUtil.isDuplicate(idempotencyKey)) {
            return Result.ok(Map.of("status", "duplicate", "message", "Already processed"));
        }
        var result = callbackService.saveShard(request);
        if (idempotencyKey != null) idempotencyUtil.mark(idempotencyKey);
        return Result.ok(result);
    }

    @PostMapping("/strategies")
    public Result<Map<String, Object>> saveStrategy(@RequestBody Map<String, Object> body, HttpServletRequest request) {
        checkApiKey(request);
        return Result.ok(callbackService.saveStrategy(body));
    }

    @PostMapping("/sessions/complete")
    public Result<Map<String, Object>> sessionComplete(@RequestBody Map<String, Object> body, HttpServletRequest request) {
        checkApiKey(request);
        return Result.ok(callbackService.sessionComplete(body));
    }

    @PostMapping("/audit")
    public Result<Map<String, Object>> writeAudit(@RequestBody Map<String, Object> body, HttpServletRequest request) {
        checkApiKey(request);
        return Result.ok(callbackService.writeAudit(body));
    }

    @PostMapping("/progress")
    public Result<Map<String, Object>> reportProgress(@RequestBody Map<String, Object> body, HttpServletRequest request) {
        checkApiKey(request);
        return Result.ok(callbackService.reportProgress(body));
    }
}
