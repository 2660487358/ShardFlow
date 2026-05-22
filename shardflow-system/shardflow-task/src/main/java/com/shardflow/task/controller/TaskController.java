package com.shardflow.task.controller;

import com.shardflow.common.entity.TaskEntity;
import com.shardflow.task.service.TaskService;
import com.shardflow.usercontext.context.UserContext;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

import java.util.List;
import java.util.Map;

@RestController
@RequestMapping("/api/v1/tasks")
public class TaskController {

    private final TaskService taskService;

    public TaskController(TaskService taskService) {
        this.taskService = taskService;
    }

    @PostMapping
    public ResponseEntity<TaskEntity> create(@RequestBody Map<String, String> body) {
        String userId = UserContext.getUserId();
        TaskEntity task = taskService.createTask(
            userId,
            body.getOrDefault("title", ""),
            body.get("description")
        );
        return ResponseEntity.ok(task);
    }

    @GetMapping
    public ResponseEntity<List<TaskEntity>> list() {
        return ResponseEntity.ok(taskService.listTasks(UserContext.getUserId()));
    }

    @GetMapping("/{taskId}")
    public ResponseEntity<TaskEntity> get(@PathVariable String taskId) {
        return taskService.getTask(taskId)
            .map(ResponseEntity::ok)
            .orElse(ResponseEntity.notFound().build());
    }

    @PutMapping("/{taskId}/status")
    public ResponseEntity<?> updateStatus(@PathVariable String taskId, @RequestBody Map<String, String> body) {
        try {
            return taskService.updateStatus(taskId, body.get("status"))
                .map(ResponseEntity::ok)
                .orElse(ResponseEntity.notFound().build());
        } catch (IllegalArgumentException | IllegalStateException e) {
            return ResponseEntity.badRequest().body(Map.of("error", e.getMessage()));
        }
    }
}
