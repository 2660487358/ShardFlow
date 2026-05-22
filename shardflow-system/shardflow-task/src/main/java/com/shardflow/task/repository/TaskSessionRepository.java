package com.shardflow.task.repository;

import com.shardflow.common.entity.TaskSessionEntity;
import org.springframework.data.jpa.repository.JpaRepository;
import java.util.List;

public interface TaskSessionRepository extends JpaRepository<TaskSessionEntity, Long> {
    List<TaskSessionEntity> findByTaskId(String taskId);
    List<TaskSessionEntity> findByUserId(String userId);
}
