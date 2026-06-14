package com.shardflow.strategy.service;

import com.shardflow.common.dto.strategy.*;

import java.util.Map;
import java.util.Optional;

/**
 * Strategy record service interface.
 * Provides CRUD operations, search, and feedback for strategy records.
 * Per P6: Strategy Record CRUD + Milvus vector operations + feedback loop.
 */
public interface StrategyRecordService {

    /**
     * Create a new strategy record.
     * Per FR-SR-001: Record tool combos, weights, reliability, success score.
     */
    StrategyCreateResponse createStrategy(StrategyCreateRequest request);

    /**
     * Get a strategy record by its ID.
     */
    Optional<StrategySearchResponse.StrategyResultItem> getStrategy(String recordId);

    /**
     * Soft-delete a strategy record.
     */
    boolean deleteStrategy(String recordId);

    /**
     * Search strategy records (structured query from MySQL).
     * Per spec section 7.8: POST /api/v1/strategy/search
     */
    StrategySearchResponse searchStrategy(StrategySearchRequest request);

    /**
     * Apply user feedback to update a strategy's success score.
     * Per FR-SR-001: User feedback loop.
     */
    Map<String, Object> applyFeedback(StrategyFeedbackRequest request);

    /**
     * Save strategy from callback (Python推理层回调).
     * Parses Map body into StrategyCreateRequest, creates or updates.
     */
    StrategyCreateResponse saveFromCallback(Map<String, Object> body);
}
