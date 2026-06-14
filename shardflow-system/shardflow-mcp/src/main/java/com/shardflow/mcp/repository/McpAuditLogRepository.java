package com.shardflow.mcp.repository;

import com.baomidou.mybatisplus.core.mapper.BaseMapper;
import com.shardflow.common.entity.McpToolAuditLogEntity;
import org.apache.ibatis.annotations.Mapper;

/**
 * MCP 工具调用审计日志 Mapper.
 * 映射 mcp_tool_audit_log 表，仅追加写入 (SEC-AUDIT-004).
 */
@Mapper
public interface McpAuditLogRepository extends BaseMapper<McpToolAuditLogEntity> {
}
