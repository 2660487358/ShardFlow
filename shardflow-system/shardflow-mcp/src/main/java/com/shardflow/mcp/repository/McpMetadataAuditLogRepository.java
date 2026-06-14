package com.shardflow.mcp.repository;

import com.baomidou.mybatisplus.core.mapper.BaseMapper;
import com.shardflow.common.entity.McpMetadataAuditLogEntity;
import org.apache.ibatis.annotations.Mapper;

/**
 * MCP 工具元数据变更审计日志 Mapper.
 * 映射 mcp_metadata_audit_log 表，仅追加写入 (SEC-AUDIT-004).
 */
@Mapper
public interface McpMetadataAuditLogRepository extends BaseMapper<McpMetadataAuditLogEntity> {
}
