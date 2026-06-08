package com.shardflow.task.service.impl;

import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import com.shardflow.common.entity.TaskEntity;
import com.shardflow.common.entity.TaskSessionEntity;
import com.shardflow.task.repository.TaskRepository;
import com.shardflow.task.repository.TaskSessionRepository;
import com.shardflow.task.service.TaskService;
import lombok.RequiredArgsConstructor;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.time.Instant;
import java.util.*;

@Service
@RequiredArgsConstructor
public class TaskServiceImpl implements TaskService {

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

    @Override
    @Transactional
    public TaskEntity createTask(String userId, String title, String description) {
        TaskEntity task = new TaskEntity();
        task.setTaskCode(UUID.randomUUID().toString());
        task.setUserId(userId);
        task.setTitle(title);
        task.setDescription(description);
        task.setStatus("PENDING");
        taskRepository.insert(task);
        return task;
    }

    @Override
    public Optional<TaskEntity> getTask(String taskCode) {
        return Optional.ofNullable(taskRepository.selectOne(
            new LambdaQueryWrapper<TaskEntity>().eq(TaskEntity::getTaskCode, taskCode)));
    }

    @Override
    public List<TaskEntity> listTasks(String userId) {
        return taskRepository.selectList(
            new LambdaQueryWrapper<TaskEntity>().eq(TaskEntity::getUserId, userId)
        );
    }

    @Override
    @Transactional
    public Optional<TaskEntity> updateStatus(String taskCode, String newStatus) {
        if (!VALID_STATUSES.contains(newStatus)) {
            throw new IllegalArgumentException("Invalid status: " + newStatus);
        }
        TaskEntity task = taskRepository.selectOne(
            new LambdaQueryWrapper<TaskEntity>().eq(TaskEntity::getTaskCode, taskCode));
        if (task == null) return Optional.empty();
        Set<String> allowed = ALLOWED_TRANSITIONS.getOrDefault(task.getStatus(), Set.of());
        if (!allowed.contains(newStatus)) {
            throw new IllegalStateException(
                "Cannot transition from " + task.getStatus() + " to " + newStatus
            );
        }
        task.setStatus(newStatus);
        task.setUpdatedAt(Instant.now());
        taskRepository.updateById(task);
        return Optional.of(task);
    }

    @Override
    @Transactional
    public TaskSessionEntity createSession(String taskId, String userId, int seq, String sourcePort) {
        TaskSessionEntity session = new TaskSessionEntity();
        session.setTaskId(taskId);
        session.setUserId(userId);
        session.setSessionSeq(seq);
        session.setSourcePort(sourcePort);
        session.setStatus("ACTIVE");
        sessionRepository.insert(session);
        return session;
    }

    @Override
    public List<TaskSessionEntity> getTaskSessions(String taskId) {
        return sessionRepository.selectList(
            new LambdaQueryWrapper<TaskSessionEntity>().eq(TaskSessionEntity::getTaskId, taskId)
        );
    }
}
