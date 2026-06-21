package com.shardflow.kb.service.impl;

import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import com.shardflow.common.entity.KbStrategyEntity;
import com.shardflow.kb.repository.KbStrategyRepository;
import com.shardflow.kb.service.StrategyService;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.stereotype.Service;

import java.util.*;

@Slf4j
@Service
@RequiredArgsConstructor
public class StrategyServiceImpl implements StrategyService {

    private final KbStrategyRepository strategyRepo;

    @Override
    public KbStrategyEntity saveStrategy(KbStrategyEntity strategy) {
        if (strategy.getStrategyId() == null || strategy.getStrategyId().isBlank()) {
            strategy.setStrategyId("strat-" + UUID.randomUUID().toString().substring(0, 8));
        }
        if (strategy.getSuccessScore() == null) {
            strategy.setSuccessScore(0.0);
        }
        if (strategy.getCostMs() == null) {
            strategy.setCostMs(0);
        }

        // 同一 task 可能多次触发策略保存（重试/多轮），基于 strategy_id 做幂等更新
        KbStrategyEntity existing = strategyRepo.selectOne(
            new LambdaQueryWrapper<KbStrategyEntity>()
                .eq(KbStrategyEntity::getStrategyId, strategy.getStrategyId()));
        if (existing != null) {
            existing.setTaskType(strategy.getTaskType());
            existing.setQueryPattern(strategy.getQueryPattern());
            existing.setSourceCombo(strategy.getSourceCombo());
            existing.setSuccessScore(strategy.getSuccessScore());
            existing.setCostMs(strategy.getCostMs());
            strategyRepo.updateById(existing);
            log.info("Strategy updated: id={}, user={}, type={}",
                    strategy.getStrategyId(), strategy.getUserId(), strategy.getTaskType());
            return existing;
        }

        strategyRepo.insert(strategy);
        log.info("Strategy saved: id={}, user={}, type={}", strategy.getStrategyId(), strategy.getUserId(), strategy.getTaskType());
        return strategy;
    }

    @Override
    public Optional<KbStrategyEntity> getByStrategyId(String strategyId) {
        return Optional.ofNullable(strategyRepo.selectOne(
            new LambdaQueryWrapper<KbStrategyEntity>().eq(KbStrategyEntity::getStrategyId, strategyId)));
    }

    @Override
    public List<KbStrategyEntity> listByUserId(String userId) {
        return strategyRepo.selectList(
            new LambdaQueryWrapper<KbStrategyEntity>()
                .eq(KbStrategyEntity::getUserId, userId)
                .orderByDesc(KbStrategyEntity::getCreatedAt));
    }

    @Override
    public List<KbStrategyEntity> searchByTaskType(String userId, String taskType) {
        return strategyRepo.selectList(
            new LambdaQueryWrapper<KbStrategyEntity>()
                .eq(KbStrategyEntity::getUserId, userId)
                .eq(KbStrategyEntity::getTaskType, taskType)
                .orderByDesc(KbStrategyEntity::getSuccessScore));
    }

    @Override
    public KbStrategyEntity updateScore(String strategyId, double score) {
        KbStrategyEntity existing = strategyRepo.selectOne(
            new LambdaQueryWrapper<KbStrategyEntity>().eq(KbStrategyEntity::getStrategyId, strategyId));
        if (existing == null) return null;
        existing.setSuccessScore(score);
        strategyRepo.updateById(existing);
        return existing;
    }
}
