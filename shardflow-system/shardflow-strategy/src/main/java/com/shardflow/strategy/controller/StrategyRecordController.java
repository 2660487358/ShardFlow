package com.shardflow.strategy.controller;

import com.shardflow.common.dto.Result;
import com.shardflow.common.dto.strategy.*;
import com.shardflow.strategy.service.StrategyRecordService;
import com.shardflow.usercontext.context.UserContext;
import jakarta.servlet.http.HttpServletRequest;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.*;
import org.springframework.web.server.ResponseStatusException;

import java.util.Map;

/**
 * REST API for strategy record management.
 *
 * Endpoints:
 * - POST   /api/v1/strategy              — Create strategy (FR-SR-001)
 * - GET    /api/v1/strategy/{recordId}    — Read strategy
 * - DELETE /api/v1/strategy/{recordId}    — Delete strategy (logical)
 * - POST   /api/v1/strategy/search        — Search strategy (spec 7.8)
 * - POST   /api/v1/strategy/feedback       — Apply feedback (FR-SR-001)
 */
@Slf4j
@RestController
@RequestMapping("/api/v1/strategy")
@RequiredArgsConstructor
public class StrategyRecordController {

    private final StrategyRecordService strategyService;

    @Value("${shardflow.java-api-key:}")
    private String javaApiKey;

    private void checkApiKey(HttpServletRequest request) {
        if (javaApiKey == null || javaApiKey.isBlank()) {
            return;
        }
        String providedKey = request.getHeader("X-API-Key");
        if (providedKey == null || !javaApiKey.equals(providedKey)) {
            throw new ResponseStatusException(HttpStatus.UNAUTHORIZED, "Invalid or missing X-API-Key");
        }
    }

    /**
     * POST /api/v1/strategy — Create a new strategy record.
     * Per FR-SR-001.
     */
    @PostMapping
    public Result<StrategyCreateResponse> create(
            @RequestBody StrategyCreateRequest request,
            HttpServletRequest httpRequest) {
        checkApiKey(httpRequest);
        if (request.getUserId() == null || request.getUserId().isBlank()) {
            request.setUserId(UserContext.getUserId());
        }
        return Result.ok(strategyService.createStrategy(request));
    }

    /**
     * GET /api/v1/strategy/{recordId} — Get strategy by ID.
     */
    @GetMapping("/{recordId}")
    public Result<StrategySearchResponse.StrategyResultItem> get(@PathVariable String recordId) {
        return strategyService.getStrategy(recordId)
                .map(Result::ok)
                .orElse(Result.fail(404, "Strategy not found"));
    }

    /**
     * DELETE /api/v1/strategy/{recordId} — Soft-delete a strategy record.
     */
    @DeleteMapping("/{recordId}")
    public Result<Void> delete(@PathVariable String recordId, HttpServletRequest httpRequest) {
        checkApiKey(httpRequest);
        boolean deleted = strategyService.deleteStrategy(recordId);
        return deleted ? Result.ok() : Result.fail(404, "Strategy not found");
    }

    /**
     * POST /api/v1/strategy/search — Search strategy records.
     * Per spec section 7.8.
     */
    @PostMapping("/search")
    public Result<StrategySearchResponse> search(
            @RequestBody StrategySearchRequest request,
            HttpServletRequest httpRequest) {
        checkApiKey(httpRequest);
        if (request.getUserId() == null || request.getUserId().isBlank()) {
            request.setUserId(UserContext.getUserId());
        }
        return Result.ok(strategyService.searchStrategy(request));
    }

    /**
     * POST /api/v1/strategy/feedback — Apply user feedback to a strategy.
     * Per FR-SR-001: User feedback loop.
     */
    @PostMapping("/feedback")
    public Result<Map<String, Object>> feedback(
            @RequestBody StrategyFeedbackRequest request,
            HttpServletRequest httpRequest) {
        checkApiKey(httpRequest);
        return Result.ok(strategyService.applyFeedback(request));
    }
}
