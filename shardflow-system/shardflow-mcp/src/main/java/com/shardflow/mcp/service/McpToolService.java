package com.shardflow.mcp.service;

import com.shardflow.common.entity.McpToolEntity;
import java.util.List;
import java.util.Map;
import java.util.Optional;

public interface McpToolService {

    List<McpToolEntity> listTools(String status);

    Optional<McpToolEntity> getTool(String toolId);

    McpToolEntity registerTool(McpToolEntity tool);

    Optional<McpToolEntity> updateTool(String toolId, McpToolEntity updates);

    boolean deleteTool(String toolId);

    List<Map<String, Object>> healthCheck();
}
