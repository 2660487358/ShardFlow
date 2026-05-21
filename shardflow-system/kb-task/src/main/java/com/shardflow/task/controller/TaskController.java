package com.shardflow.task.controller;

import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

import java.util.Map;
import java.util.UUID;
import java.util.concurrent.ConcurrentHashMap;

@RestController
@RequestMapping("/api/v1/tasks")
public class TaskController {

    private final Map<String, Map<String, Object>> tasks = new ConcurrentHashMap<>();

    @PostMapping
    public ResponseEntity<Map<String, Object>> create(@RequestBody Map<String, String> body) {
        String taskId = UUID.randomUUID().toString();
        Map<String, Object> task = Map.of(
            "task_id", taskId, "title", body.getOrDefault("title", ""),
            "status", "PENDING"
        );
        tasks.put(taskId, task);
        return ResponseEntity.ok(task);
    }

    @GetMapping("/{taskId}")
    public ResponseEntity<Map<String, Object>> get(@PathVariable String taskId) {
        return ResponseEntity.ok(tasks.getOrDefault(taskId, Map.of("error", "not found")));
    }

    @PutMapping("/{taskId}/status")
    public ResponseEntity<Map<String, Object>> updateStatus(
            @PathVariable String taskId, @RequestBody Map<String, String> body) {
        tasks.computeIfPresent(taskId, (k, v) -> {
            var m = new java.util.HashMap<>(v);
            m.put("status", body.get("status"));
            return m;
        });
        return ResponseEntity.ok(tasks.getOrDefault(taskId, Map.of("error", "not found")));
    }
}
