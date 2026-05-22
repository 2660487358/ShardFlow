package com.shardflow.common.entity;

import jakarta.persistence.*;
import java.time.Instant;

@Entity
@Table(name = "shardflow_task_session")
public class TaskSessionEntity {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "task_id", nullable = false, length = 128)
    private String taskId;

    @Column(name = "user_id", nullable = false, length = 64)
    private String userId;

    @Column(name = "session_seq", nullable = false)
    private int sessionSeq;

    @Column(name = "source_port", length = 16)
    private String sourcePort;

    @Column(length = 16, nullable = false)
    private String status = "ACTIVE";

    @Column(name = "created_at", nullable = false, updatable = false)
    private Instant createdAt = Instant.now();

    public TaskSessionEntity() {}

    public Long getId() { return id; }
    public void setId(Long id) { this.id = id; }
    public String getTaskId() { return taskId; }
    public void setTaskId(String taskId) { this.taskId = taskId; }
    public String getUserId() { return userId; }
    public void setUserId(String userId) { this.userId = userId; }
    public int getSessionSeq() { return sessionSeq; }
    public void setSessionSeq(int sessionSeq) { this.sessionSeq = sessionSeq; }
    public String getSourcePort() { return sourcePort; }
    public void setSourcePort(String sourcePort) { this.sourcePort = sourcePort; }
    public String getStatus() { return status; }
    public void setStatus(String status) { this.status = status; }
    public Instant getCreatedAt() { return createdAt; }
    public void setCreatedAt(Instant createdAt) { this.createdAt = createdAt; }
}
