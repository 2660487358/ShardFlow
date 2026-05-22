package com.shardflow.task.service;

import com.shardflow.common.entity.TaskEntity;
import com.shardflow.common.entity.TaskSessionEntity;
import com.shardflow.task.repository.TaskRepository;
import com.shardflow.task.repository.TaskSessionRepository;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.time.Instant;
import java.util.*;

@Service
public class TaskService {
    private static final Set<String> VALID_STATUSES = Set.of("PENDING", "RUNNING", "COMPLETED", "FAILED", "CANCELLED");
    private static final Map<String, Set<String>> ALLOWED_TRANSITIONS = Map.of(
        "PENDING", Set.of("RUNNING", "CANCELLED"),
        "RUNNING", Set.of("COMPLETED", "FAILED", "CANCELLED"),
        "COMPLETED", Set.of(),
        "FAILED", Set.of("RUNNING"),
        "CANCELLED", Set.of()
    );

    private final TaskRepository taskRepository;
    private final TaskSessionRepository sessionRepository;

    public TaskService(TaskRepository taskRepository, TaskSessionRepository sessionRepository) {
        this.taskRepository = taskRepository;
        this.sessionRepository = sessionRepository;
    }

    @Transactional
    public TaskEntity createTask(String userId, String title, String description) {
        TaskEntity task = new TaskEntity();
        task.setTaskId(UUID.randomUUID().toString());
        task.setUserId(userId);
        task.setTitle(title);
        task.setDescription(description);
        task.setStatus("PENDING");
        return taskRepository.save(task);
    }

    public Optional<TaskEntity> getTask(String taskId) {
        return taskRepository.findById(taskId);
    }

    public List<TaskEntity> listTasks(String userId) {
        return taskRepository.findByUserId(userId);
    }

    public List<TaskEntity> listActiveTasks(String userId) {
        return taskRepository.findByUserIdAndStatus(userId, "RUNNING");
    }

    @Transactional
    public Optional<TaskEntity> updateStatus(String taskId, String newStatus) {
        if (!VALID_STATUSES.contains(newStatus)) {
            throw new IllegalArgumentException("Invalid status: " + newStatus);
        }
        return taskRepository.findById(taskId).map(task -> {
            Set<String> allowed = ALLOWED_TRANSITIONS.getOrDefault(task.getStatus(), Set.of());
            if (!allowed.contains(newStatus)) {
                throw new IllegalStateException(
                    "Cannot transition from " + task.getStatus() + " to " + newStatus
                );
            }
            task.setStatus(newStatus);
            task.setUpdatedAt(Instant.now());
            return taskRepository.save(task);
        });
    }

    @Transactional
    public TaskSessionEntity createSession(String taskId, String userId, int seq, String sourcePort) {
        TaskSessionEntity session = new TaskSessionEntity();
        session.setTaskId(taskId);
        session.setUserId(userId);
        session.setSessionSeq(seq);
        session.setSourcePort(sourcePort);
        session.setStatus("ACTIVE");
        return sessionRepository.save(session);
    }

    public List<TaskSessionEntity> getTaskSessions(String taskId) {
        return sessionRepository.findByTaskId(taskId);
    }
}
