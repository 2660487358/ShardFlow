package com.shardflow.callback.controller;

import com.shardflow.callback.service.CallbackService;
import com.shardflow.common.dto.Result;
import jakarta.servlet.http.HttpServletRequest;
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

    /**
     * POST /api/v1/callback/shards — Save session state summary from Python推理层.
     * Per P2.3.2: Callback interface for summary persistence.
     */
    @PostMapping("/shards")
    public Result<Map<String, Object>> saveShard(@RequestBody Map<String, Object> body, HttpServletRequest request) {
        checkApiKey(request);
        return Result.ok(callbackService.saveShard(body));
    }

    /**
     * POST /api/v1/callback/profile — Save user profile from Python推理层.
     * Per P3.2.2: Callback interface for profile persistence.
     */
    @PostMapping("/profile")
    public Result<Map<String, Object>> saveProfile(@RequestBody Map<String, Object> body, HttpServletRequest request) {
        checkApiKey(request);
        return Result.ok(callbackService.saveProfile(body));
    }

    /**
     * POST /api/v1/callback/memory — Save memory chunk from Python推理层.
     * Per P4: Callback interface for memory persistence.
     */
    @PostMapping("/memory")
    public Result<Map<String, Object>> saveMemory(@RequestBody Map<String, Object> body, HttpServletRequest request) {
        checkApiKey(request);
        return Result.ok(callbackService.saveMemory(body));
    }

    /**
     * POST /api/v1/callback/strategies — Save strategy record from Python推理层.
     * Per P6.2.3: Callback interface for strategy persistence.
     */
    @PostMapping("/strategies")
    public Result<Map<String, Object>> saveStrategy(@RequestBody Map<String, Object> body, HttpServletRequest request) {
        checkApiKey(request);
        return Result.ok(callbackService.saveStrategyRecord(body));
    }
}
