package com.shardflow.common.dto.strategy;

import lombok.Data;
import lombok.NoArgsConstructor;

import java.util.List;
import java.util.Map;

/**
 * Request DTO for strategy search.
 * Per spec section 7.8: POST /api/v1/strategy/search
 */
@Data
@NoArgsConstructor
public class StrategySearchRequest {

    private String userId;

    private String query;

    private String taskType;

    private Integer topK = 3;

    private Double minSimilarity = 0.7;
}
