package com.shardflow.strategy.repository;

import com.shardflow.common.entity.StrategyEntity;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;
import org.springframework.stereotype.Repository;

import java.util.List;

@Repository
public interface StrategyRepository extends JpaRepository<StrategyEntity, String> {
    List<StrategyEntity> findByTaskTypeOrderBySuccessScoreDesc(String taskType);

    List<StrategyEntity> findByUserIdAndTaskType(String userId, String taskType);

    @Query(value = "SELECT *, 1 - (embedding_v2 <=> CAST(:queryVector AS vector)) AS similarity " +
           "FROM shardflow_strategy " +
           "WHERE user_id = :userId AND embedding_v2 IS NOT NULL " +
           "ORDER BY embedding_v2 <=> CAST(:queryVector AS vector) " +
           "LIMIT :limit", nativeQuery = true)
    List<Object[]> searchSimilar(@Param("queryVector") String queryVector,
                                 @Param("userId") String userId,
                                 @Param("limit") int limit);
}
