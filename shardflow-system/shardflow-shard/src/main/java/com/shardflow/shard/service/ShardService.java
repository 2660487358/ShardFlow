package com.shardflow.shard.service;

import com.shardflow.common.entity.ShardEntity;
import com.shardflow.shard.repository.ShardRepository;
import org.springframework.stereotype.Service;

import java.util.*;

@Service
public class ShardService {

    private final Map<String, ShardEntity> store = new LinkedHashMap<>();
    private final ShardRepository shardRepository;

    public ShardService(ShardRepository shardRepository) { this.shardRepository = shardRepository; }

    public Optional<Map<String, Object>> findByTaskId(String taskId) {
        return shardRepository.findFirstByTaskIdOrderByVersionDesc(taskId)
            .map(this::toMap);
    }

    public List<Map<String, Object>> findHistory(String taskId) {
        return shardRepository.findByTaskIdOrderByVersionAsc(taskId).stream()
            .map(this::toMap).toList();
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
