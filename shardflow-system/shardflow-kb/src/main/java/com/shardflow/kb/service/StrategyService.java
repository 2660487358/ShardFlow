package com.shardflow.kb.service;

import com.shardflow.common.entity.KbStrategyEntity;
import java.util.List;
import java.util.Optional;

public interface StrategyService {

    KbStrategyEntity saveStrategy(KbStrategyEntity strategy);

    Optional<KbStrategyEntity> getByStrategyId(String strategyId);

    List<KbStrategyEntity> listByUserId(String userId);

    List<KbStrategyEntity> searchByTaskType(String userId, String taskType);

    KbStrategyEntity updateScore(String strategyId, double score);
}
