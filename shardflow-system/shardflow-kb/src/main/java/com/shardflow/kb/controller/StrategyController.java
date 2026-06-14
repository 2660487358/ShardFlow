package com.shardflow.kb.controller;

import com.shardflow.common.dto.Result;
import com.shardflow.common.entity.KbStrategyEntity;
import com.shardflow.kb.service.StrategyService;
import com.shardflow.usercontext.context.UserContext;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.web.bind.annotation.*;

import java.util.List;
import java.util.Map;

@Slf4j
@RestController
@RequestMapping("/api/v1/strategies")
@RequiredArgsConstructor
public class StrategyController {

    private final StrategyService strategyService;

    @PostMapping
    public Result<KbStrategyEntity> saveStrategy(@RequestBody KbStrategyEntity strategy) {
        strategy.setUserId(UserContext.getUserId());
        return Result.ok(strategyService.saveStrategy(strategy));
    }

    @GetMapping
    public Result<Map<String, Object>> listStrategies(
            @RequestParam(required = false) String taskType) {
        String userId = UserContext.getUserId();
        List<KbStrategyEntity> list = taskType != null
            ? strategyService.searchByTaskType(userId, taskType)
            : strategyService.listByUserId(userId);
        return Result.ok(Map.of("strategies", list, "total", list.size()));
    }

    @GetMapping("/{strategyId}")
    public Result<?> getStrategy(@PathVariable String strategyId) {
        return strategyService.getByStrategyId(strategyId)
            .map(Result::ok)
            .orElse(Result.fail(404, "Strategy not found"));
    }

    @PostMapping("/{strategyId}/feedback")
    public Result<?> feedbackStrategy(@PathVariable String strategyId,
                                       @RequestBody Map<String, Object> payload) {
        Double score = payload.get("score") instanceof Number
            ? ((Number) payload.get("score")).doubleValue()
            : null;
        if (score == null) {
            return Result.fail(400, "score is required");
        }
        KbStrategyEntity updated = strategyService.updateScore(strategyId, score);
        if (updated == null) return Result.fail(404, "Strategy not found");
        return Result.ok(updated);
    }

    /**
     * Callback endpoint for Python agent to save strategy records.
     */
    @PostMapping("/callback")
    public Result<KbStrategyEntity> callbackSaveStrategy(@RequestBody KbStrategyEntity strategy) {
        log.info("Strategy callback: id={}, user={}, type={}",
            strategy.getStrategyId(), strategy.getUserId(), strategy.getTaskType());
        if (strategy.getUserId() == null || strategy.getUserId().isBlank()) {
            return Result.fail(400, "userId is required");
        }
        return Result.ok(strategyService.saveStrategy(strategy));
    }
}
