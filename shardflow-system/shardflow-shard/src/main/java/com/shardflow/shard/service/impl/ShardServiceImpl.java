package com.shardflow.shard.service.impl;

import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import com.shardflow.common.entity.ShardEntity;
import com.shardflow.shard.repository.ShardRepository;
import com.shardflow.shard.service.ShardService;
import lombok.RequiredArgsConstructor;
import org.springframework.stereotype.Service;

import java.util.*;

@Service
@RequiredArgsConstructor
public class ShardServiceImpl implements ShardService {

    private final ShardRepository shardRepository;

    @Override
    public Optional<Map<String, Object>> findByTaskId(String taskId) {
        ShardEntity entity = shardRepository.selectOne(
            new LambdaQueryWrapper<ShardEntity>()
                .eq(ShardEntity::getTaskId, taskId)
                .orderByDesc(ShardEntity::getVersion)
                .last("LIMIT 1")
        );
        return Optional.ofNullable(entity).map(this::toMap);
    }

    @Override
    public List<Map<String, Object>> findHistory(String taskId) {
        return shardRepository.selectList(
            new LambdaQueryWrapper<ShardEntity>()
                .eq(ShardEntity::getTaskId, taskId)
                .orderByAsc(ShardEntity::getVersion)
        ).stream().map(this::toMap).toList();
    }

    private Map<String, Object> toMap(ShardEntity e) {
        return Map.of(
            "id", e.getId(), "task_id", e.getTaskId(), "user_id", e.getUserId(),
            "session_seq", e.getSessionSeq(), "confirmed", e.getConfirmed(),
            "excluded", e.getExcluded(), "pending", e.getPending(),
            "exploration_depth", Objects.toString(e.getExplorationDepth(), ""),
            "version", e.getVersion(), "status", e.getStatus()
        );
    }
}
