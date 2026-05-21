package com.shardflow.callback.controller;

import com.shardflow.callback.service.CallbackService;
import com.shardflow.callback.util.IdempotencyUtil;
import com.shardflow.common.dto.ShardSaveRequest;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.validation.Valid;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

import java.util.Map;

@RestController
@RequestMapping("/api/v1/callback")
public class CallbackController {

    private final CallbackService callbackService;
    private final IdempotencyUtil idempotencyUtil;

    public CallbackController(CallbackService callbackService, IdempotencyUtil idempotencyUtil) {
        this.callbackService = callbackService;
        this.idempotencyUtil = idempotencyUtil;
    }

    /** Save a context shard (callback from Python推理层). Idempotent. */
    @PostMapping("/shards")
    public ResponseEntity<Map<String, Object>> saveShard(
            @Valid @RequestBody ShardSaveRequest request,
            HttpServletRequest httpRequest) {
        String idempotencyKey = httpRequest.getHeader("X-Idempotency-Key");
        if (idempotencyKey != null && idempotencyUtil.isDuplicate(idempotencyKey)) {
            return ResponseEntity.ok(Map.of("status", "duplicate", "message", "Already processed"));
        }
        var result = callbackService.saveShard(request);
        if (idempotencyKey != null) idempotencyUtil.mark(idempotencyKey);
        return ResponseEntity.ok(result);
    }

    /** Save a strategy record. */
    @PostMapping("/strategies")
    public ResponseEntity<Map<String, Object>> saveStrategy(@RequestBody Map<String, Object> body) {
        return ResponseEntity.ok(callbackService.saveStrategy(body));
    }

    /** Mark a session as completed. */
    @PostMapping("/sessions/complete")
    public ResponseEntity<Map<String, Object>> sessionComplete(@RequestBody Map<String, Object> body) {
        return ResponseEntity.ok(callbackService.sessionComplete(body));
    }

    /** Write an audit log entry. */
    @PostMapping("/audit")
    public ResponseEntity<Map<String, Object>> writeAudit(@RequestBody Map<String, Object> body) {
        return ResponseEntity.ok(callbackService.writeAudit(body));
    }

    /** Report inference progress. */
    @PostMapping("/progress")
    public ResponseEntity<Map<String, Object>> reportProgress(@RequestBody Map<String, Object> body) {
        return ResponseEntity.ok(callbackService.reportProgress(body));
    }
}
