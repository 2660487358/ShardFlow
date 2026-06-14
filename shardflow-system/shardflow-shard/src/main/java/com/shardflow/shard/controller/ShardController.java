package com.shardflow.shard.controller;

import com.shardflow.common.dto.Result;
import com.shardflow.common.dto.session.SessionSummaryCreateRequest;
import com.shardflow.common.dto.session.SessionSummaryCreateResponse;
import com.shardflow.common.entity.SessionStateSummaryEntity;
import com.shardflow.shard.service.SessionStateSummaryService;
import com.shardflow.usercontext.context.UserContext;
import jakarta.servlet.http.HttpServletRequest;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.*;
import org.springframework.web.server.ResponseStatusException;

import java.util.List;
import java.util.Map;

/**
 * REST API for session state summary management.
 *
 * Endpoints:
 * - POST   /api/v1/session-summary          — Create a new summary
 * - GET    /api/v1/session-summary/{id}      — Get summary by ID
 * - GET    /api/v1/session-summary           — List summaries (by user or user+task)
 * - PUT    /api/v1/session-summary/{id}      — Update a summary
 * - DELETE /api/v1/session-summary/{id}      — Soft-delete a summary
 */
@Slf4j
@RestController
@RequestMapping("/api/v1/session-summary")
@RequiredArgsConstructor
public class ShardController {

    private final SessionStateSummaryService summaryService;

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
     * POST /api/v1/session-summary — Create a new session state summary.
     * Per spec section 7.6.
     */
    @PostMapping
    public Result<SessionSummaryCreateResponse> create(
            @RequestBody SessionSummaryCreateRequest request,
            HttpServletRequest httpRequest) {
        checkApiKey(httpRequest);
        // If userId not set, use the authenticated user
        if (request.getUserId() == null || request.getUserId().isBlank()) {
            request.setUserId(UserContext.getUserId());
        }
        return Result.ok(summaryService.createSummary(request));
    }

    /**
     * GET /api/v1/session-summary/{summaryId} — Get summary by ID.
     */
    @GetMapping("/{summaryId}")
    public Result<SessionStateSummaryEntity> get(@PathVariable String summaryId) {
        return summaryService.getSummary(summaryId)
                .map(Result::ok)
                .orElse(Result.fail(404, "Summary not found"));
    }

    /**
     * GET /api/v1/session-summary?user_id={}&task_id={}
     * Per spec section 7.7: Load summary by user+task.
     */
    @GetMapping
    public Result<?> list(
            @RequestParam(value = "user_id", required = false) String userId,
            @RequestParam(value = "task_id", required = false) String taskId) {
        String effectiveUserId = (userId != null && !userId.isBlank())
                ? userId : UserContext.getUserId();

        if (taskId != null && !taskId.isBlank()) {
            // Load latest summary for user+task
            return summaryService.getLatestByUserAndTask(effectiveUserId, taskId)
                    .map(Result::ok)
                    .orElse(Result.fail(404, "Summary not found"));
        } else {
            // List all summaries for user
            List<SessionStateSummaryEntity> summaries = summaryService.listByUser(effectiveUserId);
            return Result.ok(Map.of("summaries", summaries, "total", summaries.size()));
        }
    }

    /**
     * GET /api/v1/session-summary/versions?user_id={}&task_id={}
     * Get version history for a task's summaries (FR-SS-004).
     */
    @GetMapping("/versions")
    public Result<?> listVersions(
            @RequestParam("user_id") String userId,
            @RequestParam("task_id") String taskId) {
        List<SessionStateSummaryEntity> versions = summaryService.listByUserAndTask(userId, taskId);
        return Result.ok(Map.of("versions", versions, "total", versions.size()));
    }

    /**
     * PUT /api/v1/session-summary/{summaryId} — Update a summary.
     */
    @PutMapping("/{summaryId}")
    public Result<SessionStateSummaryEntity> update(
            @PathVariable String summaryId,
            @RequestBody SessionSummaryCreateRequest request,
            HttpServletRequest httpRequest) {
        checkApiKey(httpRequest);
        return summaryService.updateSummary(summaryId, request)
                .map(Result::ok)
                .orElse(Result.fail(404, "Summary not found"));
    }

    /**
     * DELETE /api/v1/session-summary/{summaryId} — Soft-delete a summary.
     */
    @DeleteMapping("/{summaryId}")
    public Result<Void> delete(@PathVariable String summaryId) {
        boolean deleted = summaryService.deleteSummary(summaryId);
        return deleted ? Result.ok() : Result.fail(404, "Summary not found");
    }
}
