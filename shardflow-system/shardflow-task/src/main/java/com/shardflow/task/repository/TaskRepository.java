package com.shardflow.task.repository;

import com.shardflow.common.entity.TaskEntity;
import org.springframework.data.jpa.repository.JpaRepository;
import java.util.List;

public interface TaskRepository extends JpaRepository<TaskEntity, String> {
    List<TaskEntity> findByUserId(String userId);
    List<TaskEntity> findByStatus(String status);
    List<TaskEntity> findByUserIdAndStatus(String userId, String status);
}
