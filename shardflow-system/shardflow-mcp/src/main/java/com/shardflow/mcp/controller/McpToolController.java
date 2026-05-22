package com.shardflow.mcp.controller;

import com.shardflow.common.entity.McpToolEntity;
import com.shardflow.mcp.service.McpToolService;
import jakarta.validation.Valid;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

import java.util.List;
import java.util.Map;

@RestController
@RequestMapping("/api/v1/mcp/registry")
public class McpToolController {

    private final McpToolService service;

    public McpToolController(McpToolService service) {
        this.service = service;
    }

    @GetMapping("/tools")
    public ResponseEntity<Map<String, Object>> listTools(@RequestParam(required = false) String status) {
        List<McpToolEntity> tools = service.listTools(status);
        return ResponseEntity.ok(Map.of("tools", tools, "total", tools.size()));
    }

    @GetMapping("/tools/{toolId}")
    public ResponseEntity<McpToolEntity> getTool(@PathVariable String toolId) {
        return service.getTool(toolId)
            .map(ResponseEntity::ok)
            .orElse(ResponseEntity.notFound().build());
    }

    @PostMapping("/tools")
    public ResponseEntity<Map<String, Object>> registerTool(@Valid @RequestBody McpToolEntity tool) {
        McpToolEntity saved = service.registerTool(tool);
        return ResponseEntity.status(201).body(Map.of("tool_id", saved.getToolId(), "status", saved.getStatus()));
    }

    @PutMapping("/tools/{toolId}")
    public ResponseEntity<McpToolEntity> updateTool(@PathVariable String toolId,
                                                     @RequestBody McpToolEntity updates) {
        return service.updateTool(toolId, updates)
            .map(ResponseEntity::ok)
            .orElse(ResponseEntity.notFound().build());
    }

    @DeleteMapping("/tools/{toolId}")
    public ResponseEntity<Map<String, Object>> deleteTool(@PathVariable String toolId) {
        boolean deleted = service.deleteTool(toolId);
        if (deleted) {
            return ResponseEntity.ok(Map.of("status", "INACTIVE"));
        }
        return ResponseEntity.notFound().build();
    }

    @GetMapping("/health")
    public ResponseEntity<Map<String, Object>> healthCheck() {
        return ResponseEntity.ok(Map.of("tools", service.healthCheck()));
    }
}
