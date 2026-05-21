package com.shardflow.shard.repository;

import com.shardflow.common.entity.ShardEntity;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.stereotype.Repository;

import java.util.List;
import java.util.Optional;

@Repository
public interface ShardRepository extends JpaRepository<ShardEntity, String> {
    Optional<ShardEntity> findFirstByTaskIdOrderByVersionDesc(String taskId);
    List<ShardEntity> findByTaskIdOrderByVersionAsc(String taskId);
}
