package com.shardflow.common.entity;

import jakarta.persistence.*;
import java.time.Instant;

@Entity
@Table(name = "shardflow_shard")
public class ShardEntity {

    @Id
    @GeneratedValue(strategy = GenerationType.UUID)
    private String id;

    @Column(name = "user_id", nullable = false, length = 64)
    private String userId;

    @Column(name = "task_id", nullable = false, length = 128)
    private String taskId;

    @Column(name = "session_seq", nullable = false)
    private int sessionSeq;

    // --- New ContextShard fields (Phase 2) ---
    @Column(name = "task_type", length = 50)
    private String taskType;

    @Column(name = "task_goal", columnDefinition = "text")
    private String taskGoal;

    @Column(name = "knowledge_state", columnDefinition = "jsonb")
    private String knowledgeState;

    @Column(name = "user_context", columnDefinition = "jsonb")
    private String userContext;

    @Column(name = "execution_state", columnDefinition = "jsonb")
    private String executionState;

    // --- Legacy fields (kept for backward compatibility) ---
    @Deprecated
    @Column(columnDefinition = "jsonb", nullable = false)
    private String confirmed;

    @Deprecated
    @Column(columnDefinition = "jsonb", nullable = false)
    private String excluded;

    @Deprecated
    @Column(columnDefinition = "jsonb", nullable = false)
    private String pending;

    @Column(name = "source_preference", columnDefinition = "jsonb")
    private String sourcePreference;

    @Column(name = "exploration_depth", length = 32)
    private String explorationDepth;

    @Column(name = "key_decisions", columnDefinition = "jsonb")
    private String keyDecisions;

    @Version
    @Column(nullable = false)
    private int version;

    @Column(length = 16, nullable = false)
    private String status = "SHARDED";

    @Column(name = "created_at", nullable = false, updatable = false)
    private Instant createdAt = Instant.now();

    @Column(name = "updated_at", nullable = false)
    private Instant updatedAt = Instant.now();

    public ShardEntity() {}

    // Getters and setters
    public String getId() { return id; }
    public void setId(String id) { this.id = id; }
    public String getUserId() { return userId; }
    public void setUserId(String userId) { this.userId = userId; }
    public String getTaskId() { return taskId; }
    public void setTaskId(String taskId) { this.taskId = taskId; }
    public int getSessionSeq() { return sessionSeq; }
    public void setSessionSeq(int sessionSeq) { this.sessionSeq = sessionSeq; }
    public String getTaskType() { return taskType; }
    public void setTaskType(String taskType) { this.taskType = taskType; }
    public String getTaskGoal() { return taskGoal; }
    public void setTaskGoal(String taskGoal) { this.taskGoal = taskGoal; }
    public String getKnowledgeState() { return knowledgeState; }
    public void setKnowledgeState(String knowledgeState) { this.knowledgeState = knowledgeState; }
    public String getUserContext() { return userContext; }
    public void setUserContext(String userContext) { this.userContext = userContext; }
    public String getExecutionState() { return executionState; }
    public void setExecutionState(String executionState) { this.executionState = executionState; }
    @Deprecated public String getConfirmed() { return confirmed; }
    public void setConfirmed(String confirmed) { this.confirmed = confirmed; }
    public String getExcluded() { return excluded; }
    public void setExcluded(String excluded) { this.excluded = excluded; }
    public String getPending() { return pending; }
    public void setPending(String pending) { this.pending = pending; }
    public String getSourcePreference() { return sourcePreference; }
    public void setSourcePreference(String sourcePreference) { this.sourcePreference = sourcePreference; }
    public String getExplorationDepth() { return explorationDepth; }
    public void setExplorationDepth(String explorationDepth) { this.explorationDepth = explorationDepth; }
    public String getKeyDecisions() { return keyDecisions; }
    public void setKeyDecisions(String keyDecisions) { this.keyDecisions = keyDecisions; }
    public int getVersion() { return version; }
    public void setVersion(int version) { this.version = version; }
    public String getStatus() { return status; }
    public void setStatus(String status) { this.status = status; }
    public Instant getCreatedAt() { return createdAt; }
    public void setCreatedAt(Instant createdAt) { this.createdAt = createdAt; }
    public Instant getUpdatedAt() { return updatedAt; }
    public void setUpdatedAt(Instant updatedAt) { this.updatedAt = updatedAt; }

    @PreUpdate
    public void onUpdate() { this.updatedAt = Instant.now(); }
}
