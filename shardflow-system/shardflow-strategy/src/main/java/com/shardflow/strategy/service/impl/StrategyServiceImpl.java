package com.shardflow.strategy.service.impl;

import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import com.shardflow.common.dto.StrategySearchRequest;
import com.shardflow.common.entity.StrategyEntity;
import com.shardflow.strategy.repository.StrategyRepository;
import com.shardflow.strategy.service.StrategyService;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.stereotype.Service;

import java.util.*;
import java.util.stream.Collectors;

@Slf4j
@Service
@RequiredArgsConstructor
public class StrategyServiceImpl implements StrategyService {

    private final StrategyRepository strategyRepository;

    @Override
    public Map<String, Object> semanticSearch(StrategySearchRequest request) {
        int limit = request.limit() > 0 ? request.limit() : 5;
        return fallbackSearch(request.taskType(), limit);
    }

    private Map<String, Object> fallbackSearch(String taskType, int limit) {
        List<StrategyEntity> results = strategyRepository.selectList(
            new LambdaQueryWrapper<StrategyEntity>()
                .eq(StrategyEntity::getTaskType, taskType)
                .orderByDesc(StrategyEntity::getSuccessScore)
                .last("LIMIT " + limit)
        );

        List<Map<String, Object>> items = results.stream()
            .map(e -> Map.<String, Object>of(
                "record", Map.of(
                    "strategy_id", e.getStrategyId(),
                    "task_type", e.getTaskType(),
                    "query_pattern", Objects.toString(e.getQueryPattern(), ""),
                    "success_score", e.getSuccessScore(),
                    "cost_ms", e.getCostMs()
                ),
                "similarity", 0.5
            ))
            .collect(Collectors.toList());

        return Map.of("results", items);
    }
}
