package com.shardflow.strategy.service;

import com.shardflow.common.dto.StrategySearchRequest;
import com.shardflow.common.entity.StrategyEntity;
import com.shardflow.strategy.repository.StrategyRepository;
import org.springframework.stereotype.Service;

import java.util.*;

@Service
public class StrategyService {

    private final StrategyRepository strategyRepository;

    public StrategyService(StrategyRepository strategyRepository) {
        this.strategyRepository = strategyRepository;
    }

    public Map<String, Object> semanticSearch(StrategySearchRequest request) {
        List<StrategyEntity> results = strategyRepository
            .findByTaskTypeOrderBySuccessScoreDesc(request.taskType());

        List<Map<String, Object>> items = results.stream()
            .limit(request.limit() > 0 ? request.limit() : 5)
            .map(e -> Map.<String, Object>of(
                "record", Map.of(
                    "strategy_id", e.getStrategyId(),
                    "task_type", e.getTaskType(),
                    "query_pattern", Objects.toString(e.getQueryPattern(), ""),
                    "success_score", e.getSuccessScore(),
                    "cost_ms", e.getCostMs()
                ),
                "similarity", 0.85
            ))
            .toList();

        return Map.of("results", items);
    }
}
