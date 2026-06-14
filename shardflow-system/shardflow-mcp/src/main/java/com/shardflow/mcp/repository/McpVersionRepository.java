package com.shardflow.mcp.repository;

import com.baomidou.mybatisplus.core.mapper.BaseMapper;
import com.shardflow.common.entity.McpToolVersionEntity;
import org.apache.ibatis.annotations.Mapper;

@Mapper
public interface McpVersionRepository extends BaseMapper<McpToolVersionEntity> {
}
