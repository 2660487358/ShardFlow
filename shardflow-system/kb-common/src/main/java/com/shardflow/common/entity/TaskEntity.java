package com.shardflow.common.entity;

import jakarta.persistence.*;
import java.time.Instant;

@Entity
@Table(name = "kb_task")
public class TaskEntity {

    @Id
    @Column(name = "task_id", length = 128)
    private String taskId;

    @Column(name = "tenant_id", nullable = false, length = 64)
    private String tenantId;

    @Column(length = 512)
    private String title;

    @Column(columnDefinition = "text")
    private String description;

    @Column(length = 32, nullable = false)
    private String status = "PENDING";

    @Column(name = "session_id", length = 128)
    private String sessionId;

    @Column(name = "created_at", nullable = false, updatable = false)
    private Instant createdAt = Instant.now();

    @Column(name = "updated_at", nullable = false)
    private Instant updatedAt = Instant.now();

    public TaskEntity() {}

    public String getTaskId() { return taskId; }
    public void setTaskId(String taskId) { this.taskId = taskId; }
    public String getTenantId() { return tenantId; }
    public void setTenantId(String tenantId) { this.tenantId = tenantId; }
    public String getTitle() { return title; }
    public void setTitle(String title) { this.title = title; }
    public String getDescription() { return description; }
    public void setDescription(String description) { this.description = description; }
    public String getStatus() { return status; }
    public void setStatus(String status) { this.status = status; }
    public String getSessionId() { return sessionId; }
    public void setSessionId(String sessionId) { this.sessionId = sessionId; }
    public Instant getCreatedAt() { return createdAt; }
    public Instant getUpdatedAt() { return updatedAt; }

    @PreUpdate
    public void onUpdate() { this.updatedAt = Instant.now(); }
}
