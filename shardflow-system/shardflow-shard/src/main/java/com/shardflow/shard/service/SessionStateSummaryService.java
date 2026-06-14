package com.shardflow.shard.service;

import com.shardflow.common.dto.session.SessionSummaryCreateRequest;
import com.shardflow.common.dto.session.SessionSummaryCreateResponse;
import com.shardflow.common.entity.SessionStateSummaryEntity;

import java.util.List;
import java.util.Optional;

/**
 * Session state summary service interface.
 * Provides CRUD operations and version management for session state summaries.
 */
public interface SessionStateSummaryService {

    /**
     * Create a new session state summary.
     */
    SessionSummaryCreateResponse createSummary(SessionSummaryCreateRequest request);

    /**
     * Get a summary by its ID.
     */
    Optional<SessionStateSummaryEntity> getSummary(String summaryId);

    /**
     * Get the latest summary for a user+task combination.
     */
    Optional<SessionStateSummaryEntity> getLatestByUserAndTask(String userId, String taskId);

    /**
     * List all summaries for a user.
     */
    List<SessionStateSummaryEntity> listByUser(String userId);

    /**
     * List all summaries for a user+task combination (version history).
     */
    List<SessionStateSummaryEntity> listByUserAndTask(String userId, String taskId);

    /**
     * Update an existing summary (creates a new version).
     */
    Optional<SessionStateSummaryEntity> updateSummary(String summaryId, SessionSummaryCreateRequest request);

    /**
     * Soft-delete a summary.
     */
    boolean deleteSummary(String summaryId);

    /**
     * Save summary from callback (Python推理层回调).
     * Creates or updates based on user_id + task_id.
     */
    SessionSummaryCreateResponse saveFromCallback(SessionSummaryCreateRequest request);
}
