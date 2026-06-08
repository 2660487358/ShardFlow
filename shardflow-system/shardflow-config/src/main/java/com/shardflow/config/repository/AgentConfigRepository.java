package com.shardflow.config.repository;

import com.baomidou.mybatisplus.core.mapper.BaseMapper;
import com.shardflow.common.entity.AgentConfigEntity;
import org.apache.ibatis.annotations.Mapper;

@Mapper
public interface AgentConfigRepository extends BaseMapper<AgentConfigEntity> {
}
