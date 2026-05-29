package com.shardflow.shard.service;

import java.util.List;
import java.util.Map;
import java.util.Optional;

public interface ShardService {

    Optional<Map<String, Object>> findByTaskId(String taskId);

    List<Map<String, Object>> findHistory(String taskId);
}
