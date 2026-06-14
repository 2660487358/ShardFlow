package com.shardflow.common.dto.strategy;

import lombok.Data;
import lombok.NoArgsConstructor;

import java.util.List;
import java.util.Map;

/**
 * Response DTO for strategy search results.
 * Per spec section 7.8: Response 200 OK
 */
@Data
@NoArgsConstructor
public class StrategySearchResponse {

    private List<StrategyResultItem> results;

    private Integer total;

    private Long searchTimeMs;

    @Data
    @NoArgsConstructor
    public static class StrategyResultItem {
        private String recordId;
        private String taskType;
        private String queryPattern;
        private List<Map<String, Object>> toolCombo;
        private Double successScore;
        private Double similarityScore;
    }
}
