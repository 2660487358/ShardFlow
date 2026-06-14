package com.shardflow.common.dto.strategy;

import lombok.Data;
import lombok.NoArgsConstructor;

/**
 * Request DTO for applying user feedback to a strategy record.
 * Per FR-SR-001: User feedback loop.
 */
@Data
@NoArgsConstructor
public class StrategyFeedbackRequest {

    private String recordId;

    private String userId;

    private String toolName;

    private String feedback; // "useful" | "not_relevant"

    private Double scoreDelta;
}
