package com.shardflow.mcp.service;

import com.shardflow.common.entity.McpToolEntity;
import java.util.List;
import java.util.Map;
import java.util.Optional;

public interface McpToolService {

    List<McpToolEntity> listTools(String status);

    Optional<McpToolEntity> getTool(String toolCode);

    McpToolEntity registerTool(McpToolEntity tool);

    Optional<McpToolEntity> updateTool(String toolCode, McpToolEntity updates);

    boolean deleteTool(String toolCode);

    List<Map<String, Object>> healthCheck();
}
