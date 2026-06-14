package com.shardflow.kb.controller;

import com.shardflow.common.dto.Result;
import com.shardflow.kb.service.MilvusQueryService;
import com.shardflow.kb.service.ReconciliationService;
import com.shardflow.usercontext.context.UserContext;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.web.bind.annotation.*;

import java.util.Map;

@Slf4j
@RestController
@RequestMapping("/api/v1/kb/admin")
@RequiredArgsConstructor
public class KbAdminController {

    private final MilvusQueryService milvusQueryService;
    private final ReconciliationService reconciliationService;

    @GetMapping("/milvus/health")
    public Result<Map<String, Object>> milvusHealth() {
        return Result.ok(Map.of(
            "milvus_stable", milvusQueryService != null
        ));
    }

    @GetMapping("/milvus/stats/{kbId}")
    public Result<Map<String, Object>> milvusStats(@PathVariable String kbId) {
        String userId = UserContext.getUserId();
        return Result.ok(milvusQueryService.getStats(userId, kbId));
    }

    @PostMapping("/reconcile")
    public Result<Map<String, Object>> triggerReconciliation() {
        reconciliationService.reconcileNow();
        return Result.ok(Map.of("triggered", true));
    }
}
