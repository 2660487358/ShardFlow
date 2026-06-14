package com.shardflow.mcp.controller;

import com.shardflow.common.dto.Result;
import com.shardflow.common.dto.mcp.*;
import com.shardflow.mcp.service.McpAuditService;
import com.shardflow.mcp.service.McpToolService;
import jakarta.validation.Valid;
import lombok.RequiredArgsConstructor;
import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.*;

/**
 * MCP 工具注册中心 Controller.
 * 基路径: /api/v1/mcp/registry
 * 认证: Sa-Token JWT（前端调用） / API Key + X-User-Id（Python 推理层调用）
 */
@RestController
@RequestMapping("/api/v1/mcp/registry")
@RequiredArgsConstructor
public class McpToolController {

    private final McpToolService service;
    private final McpAuditService auditService;

    // ======================== P2.5 工具列表查询 ========================

    /**
     * 查询工具列表 (IF-001).
     * GET /api/v1/mcp/registry/tools
     */
    @GetMapping("/tools")
    public Result<ToolListResponse> listTools(ToolQueryRequest request) {
        return Result.ok(service.listTools(request));
    }

    /**
     * 查询工具详情 (IF-001).
     * GET /api/v1/mcp/registry/tools/{toolId}
     */
    @GetMapping("/tools/{toolId}")
    public Result<ToolDetailResponse> getTool(@PathVariable String toolId) {
        return service.getTool(toolId)
            .map(Result::ok)
            .orElse(Result.fail(404, "Tool not found: " + toolId));
    }

    // ======================== P2.2 工具注册 ========================

    /**
     * 注册新工具 (FR-REG-001).
     * POST /api/v1/mcp/registry/tools
     */
    @PostMapping("/tools")
    @ResponseStatus(HttpStatus.CREATED)
    public Result<ToolRegisterResponse> registerTool(@Valid @RequestBody ToolRegisterRequest request) {
        return Result.ok(service.registerTool(request));
    }

    // ======================== P2.3 工具信息管理 ========================

    /**
     * 更新工具元数据 (FR-MGMT-001).
     * PUT /api/v1/mcp/registry/tools/{toolId}
     */
    @PutMapping("/tools/{toolId}")
    public Result<ToolDetailResponse> updateTool(
            @PathVariable String toolId,
            @RequestBody ToolRegisterRequest request) {
        return Result.ok(service.updateTool(toolId, request));
    }

    /**
     * 删除工具（软删除）(FR-MGMT-002).
     * DELETE /api/v1/mcp/registry/tools/{toolId}
     */
    @DeleteMapping("/tools/{toolId}")
    public Result<Void> deleteTool(@PathVariable String toolId) {
        service.deleteTool(toolId);
        return Result.ok();
    }

    // ======================== P2.4 工具状态管理 ========================

    /**
     * 变更工具状态 (FR-STATUS-001).
     * PUT /api/v1/mcp/registry/tools/{toolId}/status
     */
    @PutMapping("/tools/{toolId}/status")
    public Result<ToolDetailResponse> changeStatus(
            @PathVariable String toolId,
            @Valid @RequestBody ToolStatusChangeRequest request) {
        return Result.ok(service.changeStatus(toolId, request));
    }

    // ======================== P3.1 工具发现（P2 阶段提前实现接口） ========================

    /**
     * 发现可用工具（仅 ACTIVE，含 Schema）(FR-DISC-001).
     * GET /api/v1/mcp/registry/tools/discover
     */
    @GetMapping("/tools/discover")
    public Result<ToolDiscoverResponse> discoverTools() {
        return Result.ok(service.discoverTools());
    }

    // ======================== P4.1 健康检查 ========================

    /**
     * 手动触发健康检查 (FR-HEALTH-002).
     * GET /api/v1/mcp/registry/tools/{toolId}/health
     */
    @GetMapping("/tools/{toolId}/health")
    public Result<ToolHealthCheckResponse> checkHealth(@PathVariable String toolId) {
        return Result.ok(service.checkHealth(toolId));
    }

    // ======================== P4.2 版本管理 ========================

    /**
     * 查询版本历史 (FR-VER-003).
     * GET /api/v1/mcp/registry/tools/{toolId}/versions
     */
    @GetMapping("/tools/{toolId}/versions")
    public Result<ToolVersionResponse> getVersions(@PathVariable String toolId) {
        return Result.ok(service.getVersionHistory(toolId));
    }

    /**
     * 版本回退 (FR-VER-004).
     * PUT /api/v1/mcp/registry/tools/{toolId}/rollback
     */
    @PutMapping("/tools/{toolId}/rollback")
    public Result<ToolDetailResponse> rollbackVersion(
            @PathVariable String toolId,
            @RequestBody ToolVersionRollbackRequest request) {
        return Result.ok(service.rollbackVersion(toolId, request));
    }

    // ======================== P5.1.7 审计日志查询 ========================

    /**
     * 查询元数据变更审计日志 (SEC-AUDIT-001).
     * GET /api/v1/mcp/registry/audit/metadata
     */
    @GetMapping("/audit/metadata")
    public Result<MetadataAuditLogResponse> queryMetadataAuditLogs(
            @RequestParam(required = false) String toolId,
            @RequestParam(required = false) String operationType,
            @RequestParam(defaultValue = "1") int page,
            @RequestParam(defaultValue = "20") int size) {
        return Result.ok(auditService.queryMetadataAuditLogs(toolId, operationType, page, size));
    }

    /**
     * 查询工具调用审计日志 (SEC-AUDIT-002).
     * GET /api/v1/mcp/registry/audit/calls
     */
    @GetMapping("/audit/calls")
    public Result<ToolCallAuditLogResponse> queryCallAuditLogs(
            @RequestParam(required = false) String toolId,
            @RequestParam(required = false) String status,
            @RequestParam(defaultValue = "1") int page,
            @RequestParam(defaultValue = "20") int size) {
        return Result.ok(auditService.queryCallAuditLogs(toolId, status, page, size));
    }
}
