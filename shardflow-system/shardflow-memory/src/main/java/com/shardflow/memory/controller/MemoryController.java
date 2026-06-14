package com.shardflow.memory.controller;

import com.shardflow.common.dto.Result;
import com.shardflow.common.dto.memory.MemoryCreateRequest;
import com.shardflow.common.dto.memory.MemoryCreateResponse;
import com.shardflow.common.dto.memory.MemorySearchRequest;
import com.shardflow.common.dto.memory.MemorySearchResponse;
import com.shardflow.common.dto.memory.MemoryUpdateResponse;
import com.shardflow.common.entity.MemoryChunkEntity;
import com.shardflow.memory.service.MemoryChunkService;
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
 * REST API for memory chunk management.
 *
 * Endpoints:
 * - POST   /api/v1/memory              — Create memory (spec 7.1)
 * - GET    /api/v1/memory/{memoryId}    — Read memory (spec 7.3)
 * - PUT    /api/v1/memory/{memoryId}    — Update memory (spec 7.4)
 * - DELETE /api/v1/memory/{memoryId}    — Delete memory (spec 7.5)
 * - POST   /api/v1/memory/search        — Search memory (spec 7.2)
 * - GET    /api/v1/memory/export         — Export memory (spec 7.10)
 */
@Slf4j
@RestController
@RequestMapping("/api/v1/memory")
@RequiredArgsConstructor
public class MemoryController {

    private final MemoryChunkService memoryService;

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
     * POST /api/v1/memory — Create a new memory chunk.
     * Per spec section 7.1.
     */
    @PostMapping
    public Result<MemoryCreateResponse> create(
            @RequestBody MemoryCreateRequest request,
            HttpServletRequest httpRequest) {
        checkApiKey(httpRequest);
        // If userId not set, use the authenticated user
        if (request.getUserId() == null || request.getUserId().isBlank()) {
            request.setUserId(UserContext.getUserId());
        }
        return Result.ok(memoryService.createMemory(request));
    }

    /**
     * GET /api/v1/memory/{memoryId} — Get memory by ID.
     * Per spec section 7.3.
     */
    @GetMapping("/{memoryId}")
    public Result<MemoryChunkEntity> get(@PathVariable String memoryId) {
        return memoryService.getMemory(memoryId)
                .map(Result::ok)
                .orElse(Result.fail(404, "Memory not found"));
    }

    /**
     * PUT /api/v1/memory/{memoryId} — Update a memory chunk.
     * Per spec section 7.4.
     */
    @PutMapping("/{memoryId}")
    public Result<MemoryUpdateResponse> update(
            @PathVariable String memoryId,
            @RequestBody MemoryCreateRequest request,
            HttpServletRequest httpRequest) {
        checkApiKey(httpRequest);
        MemoryUpdateResponse response = memoryService.updateMemory(memoryId, request);
        if (response == null) {
            return Result.fail(404, "Memory not found");
        }
        return Result.ok(response);
    }

    /**
     * DELETE /api/v1/memory/{memoryId} — Soft-delete a memory chunk.
     * Per spec section 7.5.
     */
    @DeleteMapping("/{memoryId}")
    public Result<Void> delete(@PathVariable String memoryId, HttpServletRequest httpRequest) {
        checkApiKey(httpRequest);
        boolean deleted = memoryService.deleteMemory(memoryId);
        return deleted ? Result.ok() : Result.fail(404, "Memory not found");
    }

    /**
     * POST /api/v1/memory/search — Search memory chunks.
     * Per spec section 7.2.
     */
    @PostMapping("/search")
    public Result<MemorySearchResponse> search(
            @RequestBody MemorySearchRequest request,
            HttpServletRequest httpRequest) {
        checkApiKey(httpRequest);
        // If userId not set, use the authenticated user
        if (request.getUserId() == null || request.getUserId().isBlank()) {
            request.setUserId(UserContext.getUserId());
        }
        return Result.ok(memoryService.searchMemory(request));
    }

    /**
     * GET /api/v1/memory/export — Export all memory for a user.
     * Per spec section 7.10.
     */
    @GetMapping("/export")
    public Result<Map<String, Object>> exportMemory(
            @RequestParam(value = "user_id", required = false) String userId,
            HttpServletRequest httpRequest) {
        checkApiKey(httpRequest);
        String effectiveUserId = (userId != null && !userId.isBlank())
                ? userId : UserContext.getUserId();
        return Result.ok(memoryService.exportMemory(effectiveUserId));
    }
}
