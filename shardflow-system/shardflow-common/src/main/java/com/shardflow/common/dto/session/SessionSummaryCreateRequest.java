package com.shardflow.common.dto.session;

import lombok.Data;
import lombok.NoArgsConstructor;

import java.util.List;
import java.util.Map;

/**
 * Request DTO for saving a session state summary.
 * Per spec section 7.6: POST /api/v1/session-summary
 */
@Data
@NoArgsConstructor
public class SessionSummaryCreateRequest {

    private String userId;

    private String taskId;

    private Integer sessionSeq;

    private String taskType;

    private String taskGoal;

    private KnowledgeState knowledgeState;

    private UserContext userContext;

    private ExecutionState executionState;

    private Map<String, Double> sourcePreference;

    @Data
    @NoArgsConstructor
    public static class KnowledgeState {
        private List<String> confirmed;
        private List<String> excluded;
        private List<String> pending;
        private List<KeyDecision> keyDecisions;
    }

    @Data
    @NoArgsConstructor
    public static class KeyDecision {
        private String decision;
        private String reason;
        private Double confidence;
    }

    @Data
    @NoArgsConstructor
    public static class UserContext {
        private String expertiseLevel;
        private String preferredDepth;
        private String communicationStyle;
    }

    @Data
    @NoArgsConstructor
    public static class ExecutionState {
        private Integer completedSteps;
        private String currentStep;
        private List<String> toolsUsed;
        private String estimatedRemaining;
    }
}
