package com.shardflow.shard.controller;

import com.shardflow.common.dto.Result;
import com.shardflow.shard.service.ShardService;
import lombok.RequiredArgsConstructor;
import org.springframework.web.bind.annotation.*;

@RestController
@RequestMapping("/api/v1/shards")
@RequiredArgsConstructor
public class ShardController {

    private final ShardService shardService;

    @GetMapping("/{taskId}")
    public Result<?> getLatest(@PathVariable String taskId) {
        return shardService.findByTaskId(taskId)
            .map(Result::ok)
            .orElse(Result.fail(404, "Shard not found"));
    }

    @GetMapping("/{taskId}/history")
    public Result<?> getHistory(@PathVariable String taskId) {
        return Result.ok(shardService.findHistory(taskId));
    }
}
