package com.shardflow.strategy.service.impl;

import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import com.shardflow.common.dto.StrategySearchRequest;
import com.shardflow.common.entity.StrategyEntity;
import com.shardflow.strategy.milvus.MilvusClientService;
import com.shardflow.strategy.repository.StrategyRepository;
import com.shardflow.strategy.service.EmbeddingService;
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
    private final EmbeddingService embeddingService;
    private final MilvusClientService milvusClient;

    @Override
    public Map<String, Object> semanticSearch(StrategySearchRequest request) {
        int limit = request.limit() > 0 ? request.limit() : 5;

        // Try Milvus vector search first
        List<Float> queryVector = embeddingService.generate(request.query() != null ? request.query() : request.taskType());
        if (queryVector != null) {
            List<Map<String, Object>> milvusResults = milvusClient.search(
                "strategy_vectors", queryVector, limit * 2, "strategy_id");
            if (!milvusResults.isEmpty()) {
                List<Map<String, Object>> items = new ArrayList<>();
                Set<String> seenIds = new HashSet<>();
                for (Map<String, Object> r : milvusResults) {
                    String strategyCode = (String) r.get("strategy_id");
                    if (strategyCode == null || seenIds.contains(strategyCode)) continue;
                    seenIds.add(strategyCode);
                    StrategyEntity entity = strategyRepository.selectOne(
                        new LambdaQueryWrapper<StrategyEntity>().eq(StrategyEntity::getStrategyCode, strategyCode));
                    if (entity != null) {
                        double similarity = 1.0 - (Double) r.getOrDefault("distance", 0.5);
                        items.add(Map.of(
                            "record", Map.of(
                                "strategy_id", entity.getStrategyCode(),
                                "task_type", entity.getTaskType(),
                                "query_pattern", Objects.toString(entity.getQueryPattern(), ""),
                                "success_score", entity.getSuccessScore(),
                                "cost_ms", entity.getCostMs()
                            ),
                            "similarity", Math.max(0, Math.min(1, similarity))
                        ));
                    }
                    if (items.size() >= limit) break;
                }
                if (!items.isEmpty()) {
                    return Map.of("results", items);
                }
            }
        }

        // Fallback to keyword search
        log.info("Milvus search unavailable or returned no results, using fallback search");
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
                    "strategy_id", e.getStrategyCode(),
                    "task_type", e.getTaskType(),
                    "query_pattern", Objects.toString(e.getQueryPattern(), ""),
                    "success_score", e.getSuccessScore(),
                    "cost_ms", e.getCostMs()
                ),
                "similarity", e.getSuccessScore()
            ))
            .collect(Collectors.toList());

        return Map.of("results", items);
    }
}
