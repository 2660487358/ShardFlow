package com.shardflow.callback.controller;

import com.shardflow.callback.service.CallbackService;
import com.shardflow.callback.util.IdempotencyUtil;
import com.shardflow.common.dto.Result;
import jakarta.servlet.http.HttpServletRequest;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.*;
import org.springframework.web.server.ResponseStatusException;

import java.util.Map;
import java.util.Optional;
import java.util.function.Supplier;

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

    /**
     * 提取幂等键（C-4.20）。
     * <p>
     * 优先使用 X-Request-ID 头部，其次使用 body 中的 request_id 字段。
     * 与 user_id 组合形成复合键，避免跨用户碰撞。
     */
    private String extractIdempotencyKey(HttpServletRequest request, Map<String, Object> body) {
        String requestId = request.getHeader("X-Request-ID");
        if ((requestId == null || requestId.isBlank()) && body != null) {
            Object rid = body.get("request_id");
            if (rid instanceof String s) requestId = s;
        }
        if (requestId == null || requestId.isBlank()) return null;
        String userId = body != null ? (String) body.get("user_id") : null;
        return IdempotencyUtil.buildKey(userId, requestId);
    }

    /**
     * 幂等执行包装器（C-4.8 回调接口幂等）。
     * <p>
     * 流程：
     * 1. 提取幂等键，若不存在则直接执行（向后兼容）。
     * 2. tryAcquire 抢占：成功则执行业务并缓存响应；失败则返回缓存的首次响应。
     * 3. 业务异常时释放幂等键，允许 Python 端重试。
     */
    private Result<Map<String, Object>> executeIdempotent(
            HttpServletRequest request, Map<String, Object> body, Supplier<Map<String, Object>> action) {
        return executeIdempotentByKey(extractIdempotencyKey(request, body), action);
    }

    /**
     * 幂等执行包装器（DELETE 等无 body 接口专用）。
     * 从 X-Request-ID 头部提取幂等键，与 userId 组合。
     */
    private Result<Map<String, Object>> executeIdempotent(
            HttpServletRequest request, String userId, Supplier<Map<String, Object>> action) {
        String requestId = request.getHeader("X-Request-ID");
        String key = (requestId == null || requestId.isBlank())
                ? null
                : IdempotencyUtil.buildKey(userId, requestId);
        return executeIdempotentByKey(key, action);
    }

    /**
     * 幂等执行核心逻辑。
     *
     * @param idempotencyKey 幂等键，null 表示无幂等键（向后兼容直接执行）
     */
    private Result<Map<String, Object>> executeIdempotentByKey(
            String idempotencyKey, Supplier<Map<String, Object>> action) {
        // 无幂等键：直接执行（向后兼容旧客户端）
        if (idempotencyKey == null) {
            return Result.ok(action.get());
        }

        // 重复请求：返回缓存的首次响应
        Optional<Map<String, Object>> cached = idempotencyUtil.getCachedResponse(idempotencyKey);
        if (cached.isPresent()) {
            log.info("Idempotent replay: key={}, returning cached response", idempotencyKey);
            return Result.ok(cached.get());
        }

        // 首次请求：抢占幂等键
        if (!idempotencyUtil.tryAcquire(idempotencyKey)) {
            // 抢占失败但无缓存响应：说明另一并发请求正在处理
            log.warn("Idempotent key busy (concurrent): key={}", idempotencyKey);
            throw new ResponseStatusException(HttpStatus.CONFLICT, "Concurrent idempotent request in progress");
        }

        // 执行业务
        try {
            Map<String, Object> response = action.get();
            idempotencyUtil.storeResponse(idempotencyKey, response);
            return Result.ok(response);
        } catch (RuntimeException e) {
            // 业务失败：释放幂等键，允许重试
            idempotencyUtil.release(idempotencyKey);
            throw e;
        }
    }

    @PostMapping("/sessions/complete")
    public Result<Map<String, Object>> sessionComplete(@RequestBody Map<String, Object> body, HttpServletRequest request) {
        checkApiKey(request);
        return executeIdempotent(request, body, () -> callbackService.sessionComplete(body));
    }

    @PostMapping("/audit")
    public Result<Map<String, Object>> writeAudit(@RequestBody Map<String, Object> body, HttpServletRequest request) {
        checkApiKey(request);
        return executeIdempotent(request, body, () -> callbackService.writeAudit(body));
    }

    @PostMapping("/progress")
    public Result<Map<String, Object>> reportProgress(@RequestBody Map<String, Object> body, HttpServletRequest request) {
        checkApiKey(request);
        return executeIdempotent(request, body, () -> callbackService.reportProgress(body));
    }

    /**
     * POST /api/v1/callback/shards — Save session state summary from Python推理层.
     * Per P2.3.2: Callback interface for summary persistence.
     */
    @PostMapping("/shards")
    public Result<Map<String, Object>> saveShard(@RequestBody Map<String, Object> body, HttpServletRequest request) {
        checkApiKey(request);
        return executeIdempotent(request, body, () -> callbackService.saveShard(body));
    }

    /**
     * POST /api/v1/callback/profile — Save user profile from Python推理层.
     * Per P3.2.2: Callback interface for profile persistence.
     */
    @PostMapping("/profile")
    public Result<Map<String, Object>> saveProfile(@RequestBody Map<String, Object> body, HttpServletRequest request) {
        checkApiKey(request);
        return executeIdempotent(request, body, () -> callbackService.saveProfile(body));
    }

    /**
     * POST /api/v1/callback/memory — Save memory chunk from Python推理层.
     * Per P4: Callback interface for memory persistence.
     */
    @PostMapping("/memory")
    public Result<Map<String, Object>> saveMemory(@RequestBody Map<String, Object> body, HttpServletRequest request) {
        checkApiKey(request);
        return executeIdempotent(request, body, () -> callbackService.saveMemory(body));
    }

    /**
     * POST /api/v1/callback/strategies — Save strategy record from Python推理层.
     * Per P6.2.3: Callback interface for strategy persistence.
     */
    @PostMapping("/strategies")
    public Result<Map<String, Object>> saveStrategy(@RequestBody Map<String, Object> body, HttpServletRequest request) {
        checkApiKey(request);
        return executeIdempotent(request, body, () -> callbackService.saveStrategyRecord(body));
    }

    // ===== S4.6 新增回调接口 CB-08~CB-12 + kb-shard =====

    /**
     * CB-08: 记忆删除回调。
     * DELETE /api/v1/callback/memory/{key}
     */
    @DeleteMapping("/memory/{key}")
    public Result<Map<String, Object>> deleteMemory(
            @PathVariable String key,
            @RequestParam(required = false) String userId,
            HttpServletRequest request) {
        checkApiKey(request);
        return executeIdempotent(request, userId, () -> callbackService.deleteMemory(userId, key));
    }

    /**
     * CB-09: 会话摘要回调。
     * POST /api/v1/callback/session-summary
     * Python 生成摘要后回调 Java 异步归档 PG。
     */
    @PostMapping("/session-summary")
    public Result<Map<String, Object>> saveSessionSummary(@RequestBody Map<String, Object> body, HttpServletRequest request) {
        checkApiKey(request);
        return executeIdempotent(request, body, () -> callbackService.saveSessionSummary(body));
    }

    // CB-10 工具执行日志回调（POST /api/v1/callback/mcp/audit）已由
    // com.shardflow.mcp.controller.McpCallbackController#audit 承接，
    // 写入专用 mcp_tool_audit_log 表（SEC-AUDIT-002），此处不再重复映射。

    /**
     * CB-11: 策略删除回调。
     * DELETE /api/v1/callback/strategies/{recordId}
     */
    @DeleteMapping("/strategies/{recordId}")
    public Result<Map<String, Object>> deleteStrategy(@PathVariable String recordId, HttpServletRequest request) {
        checkApiKey(request);
        return executeIdempotent(request, (String) null, () -> callbackService.deleteStrategy(recordId));
    }

    /**
     * CB-12: 策略保存回调（显式 save 路径）。
     * POST /api/v1/callback/strategies/save
     */
    @PostMapping("/strategies/save")
    public Result<Map<String, Object>> saveStrategyExplicit(@RequestBody Map<String, Object> body, HttpServletRequest request) {
        checkApiKey(request);
        return executeIdempotent(request, body, () -> callbackService.saveStrategy(body));
    }

    /**
     * KB Shard 状态包回调（C-4.5）。
     * POST /api/v1/callback/kb-shard
     * Python 推理层通过回调写入/更新状态包。
     */
    @PostMapping("/kb-shard")
    public Result<Map<String, Object>> saveKbShard(@RequestBody Map<String, Object> body, HttpServletRequest request) {
        checkApiKey(request);
        return executeIdempotent(request, body, () -> callbackService.saveKbShard(body));
    }
}
