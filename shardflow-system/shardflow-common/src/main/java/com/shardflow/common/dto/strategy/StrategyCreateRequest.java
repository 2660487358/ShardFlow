package com.shardflow.common.dto.strategy;

import lombok.Data;
import lombok.NoArgsConstructor;

import java.util.List;
import java.util.Map;

/**
 * Request DTO for creating a new strategy record.
 * Per spec section 6.3 and FR-SR-001.
 */
@Data
@NoArgsConstructor
public class StrategyCreateRequest {

    private String recordId;

    private String userId;

    private String taskType;

    private String queryPattern;

    private List<ToolComboItem> toolCombo;

    private Map<String, String> userFeedback;

    private Double successScore;

    private Integer costMs;

    @Data
    @NoArgsConstructor
    public static class ToolComboItem {
        private String tool;
        private Double weight;
        private Double reliability;
    }
}
