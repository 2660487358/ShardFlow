package com.shardflow.strategy.controller;

import com.shardflow.common.dto.Result;
import com.shardflow.common.dto.StrategySearchRequest;
import com.shardflow.strategy.service.StrategyService;
import lombok.RequiredArgsConstructor;
import org.springframework.web.bind.annotation.*;

import java.util.Map;

@RestController
@RequestMapping("/api/v1/strategies")
@RequiredArgsConstructor
public class StrategyController {

    private final StrategyService strategyService;

    @PostMapping("/search")
    public Result<Map<String, Object>> search(@RequestBody StrategySearchRequest request) {
        return Result.ok(strategyService.semanticSearch(request));
    }

    @PostMapping("/{id}/feedback")
    public Result<Map<String, Object>> feedback(@PathVariable String id, @RequestBody Map<String, String> body) {
        return Result.ok(Map.of("success", true));
    }
}
