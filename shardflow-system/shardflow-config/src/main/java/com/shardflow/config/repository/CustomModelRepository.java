package com.shardflow.config.repository;

import com.baomidou.mybatisplus.core.mapper.BaseMapper;
import com.shardflow.common.entity.CustomModelEntity;
import org.apache.ibatis.annotations.Mapper;

@Mapper
public interface CustomModelRepository extends BaseMapper<CustomModelEntity> {
}
