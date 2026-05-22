package com.shardflow.common.entity;

import jakarta.persistence.*;
import java.time.Instant;

@Entity
@Table(name = "kb_shard")
public class ShardEntity {

    @Id
    @GeneratedValue(strategy = GenerationType.UUID)
    private String id;

    @Column(name = "tenant_id", nullable = false, length = 64)
    private String tenantId;

    @Column(name = "task_id", nullable = false, length = 128)
    private String taskId;

    @Column(name = "session_seq", nullable = false)
    private int sessionSeq;

    @Column(columnDefinition = "jsonb", nullable = false)
    private String confirmed;

    @Column(columnDefinition = "jsonb", nullable = false)
    private String excluded;

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
    public String getTenantId() { return tenantId; }
    public void setTenantId(String tenantId) { this.tenantId = tenantId; }
    public String getTaskId() { return taskId; }
    public void setTaskId(String taskId) { this.taskId = taskId; }
    public int getSessionSeq() { return sessionSeq; }
    public void setSessionSeq(int sessionSeq) { this.sessionSeq = sessionSeq; }
    public String getConfirmed() { return confirmed; }
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
