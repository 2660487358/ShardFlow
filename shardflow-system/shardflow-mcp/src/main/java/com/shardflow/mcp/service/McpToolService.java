package com.shardflow.mcp.service;

import com.shardflow.common.dto.mcp.*;
import com.shardflow.common.entity.McpToolEntity;

import java.util.Optional;

/**
 * MCP 工具注册中心服务接口.
 * P2 阶段：工具注册、信息管理、状态管理、列表查询.
 * P4 阶段：健康检查、版本管理.
 */
public interface McpToolService {

    /**
     * 注册新工具 (FR-REG-001).
     */
    ToolRegisterResponse registerTool(ToolRegisterRequest request);

    /**
     * 更新工具元数据 (FR-MGMT-001).
     */
    ToolDetailResponse updateTool(String toolId, ToolRegisterRequest request);

    /**
     * 软删除工具 (FR-MGMT-002).
     */
    boolean deleteTool(String toolId);

    /**
     * 变更工具状态 (FR-STATUS-001).
     */
    ToolDetailResponse changeStatus(String toolId, ToolStatusChangeRequest request);

    /**
     * 查询工具列表 (IF-001).
     */
    ToolListResponse listTools(ToolQueryRequest request);

    /**
     * 查询工具详情 (IF-001).
     */
    Optional<ToolDetailResponse> getTool(String toolId);

    /**
     * 发现可用工具（仅 ACTIVE，含 Schema）(FR-DISC-001).
     */
    ToolDiscoverResponse discoverTools();

    /**
     * 获取原始实体（内部使用）.
     */
    Optional<McpToolEntity> getToolEntity(String toolId);

    // ======================== P4 健康检查 ========================

    /**
     * 手动触发健康检查 (FR-HEALTH-002).
     */
    ToolHealthCheckResponse checkHealth(String toolId);

    // ======================== P4 版本管理 ========================

    /**
     * 查询版本历史 (FR-VER-003).
     */
    ToolVersionResponse getVersionHistory(String toolId);

    /**
     * 版本回退 (FR-VER-004).
     */
    ToolDetailResponse rollbackVersion(String toolId, ToolVersionRollbackRequest request);
}
