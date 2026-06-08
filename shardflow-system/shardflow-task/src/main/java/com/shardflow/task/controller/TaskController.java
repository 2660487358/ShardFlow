package com.shardflow.task.controller;

import com.shardflow.common.dto.Result;
import com.shardflow.common.entity.TaskEntity;
import com.shardflow.common.entity.TaskSessionEntity;
import com.shardflow.task.service.TaskService;
import com.shardflow.usercontext.context.UserContext;
import lombok.RequiredArgsConstructor;
import org.springframework.web.bind.annotation.*;

import java.util.List;
import java.util.Map;

@RestController
@RequestMapping("/api/v1/tasks")
@RequiredArgsConstructor
public class TaskController {

    private final TaskService taskService;

    @PostMapping
    public Result<TaskEntity> create(@RequestBody Map<String, String> body) {
        TaskEntity task = taskService.createTask(
            UserContext.getUserId(),
            body.getOrDefault("title", ""),
            body.get("description")
        );
        return Result.ok(task);
    }

    @GetMapping
    public Result<?> list() {
        return Result.ok(taskService.listTasks(UserContext.getUserId()));
    }

    @GetMapping("/{taskId}")
    public Result<?> get(@PathVariable String taskId) {
        return taskService.getTask(taskId)
            .map(Result::ok)
            .orElse(Result.fail(404, "Task not found"));
    }

    @PutMapping("/{taskId}/status")
    public Result<?> updateStatus(@PathVariable String taskId, @RequestBody Map<String, String> body) {
        try {
            return taskService.updateStatus(taskId, body.get("status"))
                .map(Result::ok)
                .orElse(Result.fail(404, "Task not found"));
        } catch (IllegalArgumentException | IllegalStateException e) {
            return Result.fail(400, e.getMessage());
        }
    }

    @PostMapping("/{taskId}/sessions")
    public Result<TaskSessionEntity> createSession(@PathVariable String taskId, @RequestBody Map<String, Object> body) {
        String sourcePort = body.getOrDefault("source_port", "Web").toString();
        int seq = body.containsKey("seq") ? ((Number) body.get("seq")).intValue() : 1;
        TaskSessionEntity session = taskService.createSession(taskId, UserContext.getUserId(), seq, sourcePort);
        return Result.ok(session);
    }

    @GetMapping("/{taskId}/sessions")
    public Result<Map<String, Object>> getTaskSessions(@PathVariable String taskId) {
        List<TaskSessionEntity> sessions = taskService.getTaskSessions(taskId);
        return Result.ok(Map.of("sessions", sessions, "total", sessions.size()));
    }
}
