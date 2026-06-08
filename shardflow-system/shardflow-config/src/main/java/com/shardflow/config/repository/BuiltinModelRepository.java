package com.shardflow.config.repository;

import com.baomidou.mybatisplus.core.mapper.BaseMapper;
import com.shardflow.common.entity.BuiltinModelEntity;
import org.apache.ibatis.annotations.Mapper;

@Mapper
public interface BuiltinModelRepository extends BaseMapper<BuiltinModelEntity> {
}
