package com.shardflow.shard.controller;

import com.shardflow.shard.service.ShardService;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

import java.util.Map;

@RestController
@RequestMapping("/api/v1/shards")
public class ShardController {

    private final ShardService shardService;

    public ShardController(ShardService shardService) { this.shardService = shardService; }

    @GetMapping("/{taskId}")
    public ResponseEntity<Map<String, Object>> getLatest(@PathVariable String taskId) {
        return shardService.findByTaskId(taskId)
            .map(ResponseEntity::ok)
            .orElse(ResponseEntity.notFound().build());
    }

    @GetMapping("/{taskId}/history")
    public ResponseEntity<Object> getHistory(@PathVariable String taskId) {
        return ResponseEntity.ok(shardService.findHistory(taskId));
    }
}
