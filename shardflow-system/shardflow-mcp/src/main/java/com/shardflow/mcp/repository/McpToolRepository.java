package com.shardflow.mcp.repository;

import com.baomidou.mybatisplus.core.mapper.BaseMapper;
import com.shardflow.common.entity.McpToolEntity;
import org.apache.ibatis.annotations.Mapper;

@Mapper
public interface McpToolRepository extends BaseMapper<McpToolEntity> {
}
