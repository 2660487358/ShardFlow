package com.shardflow.strategy.service;

import com.shardflow.common.dto.StrategySearchRequest;
import com.shardflow.common.entity.StrategyEntity;
import com.shardflow.strategy.repository.StrategyRepository;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;

import java.util.*;

@Service
public class StrategyService {
    private static final Logger log = LoggerFactory.getLogger(StrategyService.class);

    private final StrategyRepository strategyRepository;
    private final EmbeddingService embeddingService;

    public StrategyService(StrategyRepository strategyRepository, EmbeddingService embeddingService) {
        this.strategyRepository = strategyRepository;
        this.embeddingService = embeddingService;
    }

    public Map<String, Object> semanticSearch(StrategySearchRequest request) {
        int limit = request.limit() > 0 ? request.limit() : 5;

        if (request.embedding() != null && request.embedding().length > 0) {
            try {
                String vectorStr = embeddingService.toVectorString(
                    Arrays.stream(request.embedding()).boxed().toList()
                );
                List<Object[]> rows = strategyRepository.searchSimilar(
                    vectorStr, "default", limit
                );
                if (!rows.isEmpty()) {
                    List<Map<String, Object>> items = new ArrayList<>();
                    for (Object[] row : rows) {
                        StrategyEntity e = (StrategyEntity) row[0];
                        Double similarity = row.length > 1 ? ((Number) row[1]).doubleValue() : 0.0;
                        items.add(Map.of(
                            "record", Map.of(
                                "strategy_id", e.getStrategyId(),
                                "task_type", e.getTaskType(),
                                "query_pattern", Objects.toString(e.getQueryPattern(), ""),
                                "success_score", e.getSuccessScore(),
                                "cost_ms", e.getCostMs()
                            ),
                            "similarity", Math.round(similarity * 100.0) / 100.0
                        ));
                    }
                    return Map.of("results", items);
                }
            } catch (Exception e) {
                log.warn("Vector search failed, falling back to task_type match: {}", e.getMessage());
            }
        }

        return fallbackSearch(request.taskType(), limit);
    }

    private Map<String, Object> fallbackSearch(String taskType, int limit) {
        List<StrategyEntity> results = strategyRepository
            .findByTaskTypeOrderBySuccessScoreDesc(taskType);

        List<Map<String, Object>> items = results.stream()
            .limit(limit)
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
            .toList();

        return Map.of("results", items);
    }
}
