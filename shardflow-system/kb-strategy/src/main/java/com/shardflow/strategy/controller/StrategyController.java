package com.shardflow.strategy.controller;

import com.shardflow.common.dto.StrategySearchRequest;
import com.shardflow.strategy.service.StrategyService;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

import java.util.Map;

@RestController
@RequestMapping("/api/v1/strategies")
public class StrategyController {

    private final StrategyService strategyService;

    public StrategyController(StrategyService strategyService) { this.strategyService = strategyService; }

    @PostMapping("/search")
    public ResponseEntity<Map<String, Object>> search(@RequestBody StrategySearchRequest request) {
        return ResponseEntity.ok(strategyService.semanticSearch(request));
    }
}
