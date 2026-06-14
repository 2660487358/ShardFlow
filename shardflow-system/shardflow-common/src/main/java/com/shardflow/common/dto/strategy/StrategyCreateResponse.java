package com.shardflow.common.dto.strategy;

import lombok.Data;
import lombok.NoArgsConstructor;

/**
 * Response DTO for creating a strategy record.
 * Per spec section 6.3 and FR-SR-001.
 */
@Data
@NoArgsConstructor
public class StrategyCreateResponse {

    private String recordId;

    private String status;

    private Double successScore;

    public static StrategyCreateResponse created(String recordId, Double successScore) {
        StrategyCreateResponse response = new StrategyCreateResponse();
        response.setRecordId(recordId);
        response.setStatus("created");
        response.setSuccessScore(successScore);
        return response;
    }
}
