package com.shardflow.strategy.repository;

import com.shardflow.common.entity.StrategyEntity;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.stereotype.Repository;

import java.util.List;

@Repository
public interface StrategyRepository extends JpaRepository<StrategyEntity, String> {
    List<StrategyEntity> findByTaskTypeOrderBySuccessScoreDesc(String taskType);
}
