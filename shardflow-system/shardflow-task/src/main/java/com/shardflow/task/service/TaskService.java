package com.shardflow.task.service;

import com.shardflow.common.entity.TaskEntity;
import com.shardflow.common.entity.TaskSessionEntity;
import java.util.List;
import java.util.Optional;

public interface TaskService {

    TaskEntity createTask(String userId, String title, String description);

    Optional<TaskEntity> getTask(String taskCode);

    List<TaskEntity> listTasks(String userId);

    Optional<TaskEntity> updateStatus(String taskCode, String newStatus);

    TaskSessionEntity createSession(String taskCode, String userId, int seq, String sourcePort);

    List<TaskSessionEntity> getTaskSessions(String taskCode);
}
