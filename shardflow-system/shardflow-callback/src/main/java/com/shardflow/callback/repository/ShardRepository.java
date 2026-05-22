package com.shardflow.callback.repository;

import com.shardflow.common.entity.ShardEntity;
import org.springframework.data.jpa.repository.JpaRepository;
import java.util.Optional;

public interface ShardRepository extends JpaRepository<ShardEntity, String> {
    Optional<ShardEntity> findByUserIdAndTaskId(String userId, String taskId);
}
