package com.shardflow.mcp.controller;

import com.shardflow.common.dto.Result;
import com.shardflow.common.entity.McpToolEntity;
import com.shardflow.mcp.service.McpToolService;
import jakarta.validation.Valid;
import lombok.RequiredArgsConstructor;
import org.springframework.web.bind.annotation.*;

import java.util.List;
import java.util.Map;

@RestController
@RequestMapping("/api/v1/mcp/registry")
@RequiredArgsConstructor
public class McpToolController {

    private final McpToolService service;

    @GetMapping("/tools")
    public Result<Map<String, Object>> listTools(@RequestParam(required = false) String status) {
        List<McpToolEntity> tools = service.listTools(status);
        return Result.ok(Map.of("tools", tools, "total", tools.size()));
    }

    @GetMapping("/tools/{toolId}")
    public Result<?> getTool(@PathVariable String toolId) {
        return service.getTool(toolId)
            .map(Result::ok)
            .orElse(Result.fail(404, "Tool not found"));
    }

    @PostMapping("/tools")
    public Result<Map<String, Object>> registerTool(@Valid @RequestBody McpToolEntity tool) {
        McpToolEntity saved = service.registerTool(tool);
        return Result.ok(Map.of("tool_id", saved.getToolId(), "status", saved.getStatus()));
    }

    @PutMapping("/tools/{toolId}")
    public Result<?> updateTool(@PathVariable String toolId, @RequestBody McpToolEntity updates) {
        return service.updateTool(toolId, updates)
            .map(Result::ok)
            .orElse(Result.fail(404, "Tool not found"));
    }

    @DeleteMapping("/tools/{toolId}")
    public Result<?> deleteTool(@PathVariable String toolId) {
        boolean deleted = service.deleteTool(toolId);
        if (deleted) {
            return Result.ok(Map.of("status", "INACTIVE"));
        }
        return Result.fail(404, "Tool not found");
    }

    @GetMapping("/health")
    public Result<Map<String, Object>> healthCheck() {
        return Result.ok(Map.of("tools", service.healthCheck()));
    }
}
