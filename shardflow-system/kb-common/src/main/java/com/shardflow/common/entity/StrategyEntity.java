package com.shardflow.common.entity;

import jakarta.persistence.*;
import java.time.Instant;

@Entity
@Table(name = "kb_strategy")
public class StrategyEntity {

    @Id
    @Column(name = "strategy_id", length = 128)
    private String strategyId;

    @Column(name = "tenant_id", nullable = false, length = 64)
    private String tenantId;

    @Column(name = "task_type", nullable = false, length = 64)
    private String taskType;

    @Column(name = "query_pattern", length = 1024)
    private String queryPattern;

    @Column(name = "source_combo", columnDefinition = "jsonb")
    private String sourceCombo;

    @Column(name = "success_score")
    private double successScore;

    @Column(name = "cost_ms")
    private int costMs;

    @Column(columnDefinition = "vector(1536)")
    private String embedding;

    @Column(name = "created_at", nullable = false, updatable = false)
    private Instant createdAt = Instant.now();

    public StrategyEntity() {}

    public String getStrategyId() { return strategyId; }
    public void setStrategyId(String strategyId) { this.strategyId = strategyId; }
    public String getTenantId() { return tenantId; }
    public void setTenantId(String tenantId) { this.tenantId = tenantId; }
    public String getTaskType() { return taskType; }
    public void setTaskType(String taskType) { this.taskType = taskType; }
    public String getQueryPattern() { return queryPattern; }
    public void setQueryPattern(String queryPattern) { this.queryPattern = queryPattern; }
    public String getSourceCombo() { return sourceCombo; }
    public void setSourceCombo(String sourceCombo) { this.sourceCombo = sourceCombo; }
    public double getSuccessScore() { return successScore; }
    public void setSuccessScore(double successScore) { this.successScore = successScore; }
    public int getCostMs() { return costMs; }
    public void setCostMs(int costMs) { this.costMs = costMs; }
    public String getEmbedding() { return embedding; }
    public void setEmbedding(String embedding) { this.embedding = embedding; }
    public Instant getCreatedAt() { return createdAt; }
    public void setCreatedAt(Instant createdAt) { this.createdAt = createdAt; }
}
