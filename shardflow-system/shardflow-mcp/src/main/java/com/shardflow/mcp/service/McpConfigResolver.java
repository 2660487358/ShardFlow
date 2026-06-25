package com.shardflow.mcp.service;

import com.shardflow.common.dto.mcp.QuickConfigRequest;
import com.shardflow.common.dto.mcp.ToolRegisterResponse;

/**
 * MCP 配置解析器服务接口.
 * P2 阶段：将 QuickConfigRequest + 模板展开为完整配置并注册.
 */
public interface McpConfigResolver {

    /**
     * 快速配置注册.
     * 将 QuickConfigRequest + 模板展开为 ToolRegisterRequest 并委托现有服务注册.
     *
     * @param request 快速配置请求
     * @return 注册响应
     */
    ToolRegisterResponse resolveAndRegister(QuickConfigRequest request);
}