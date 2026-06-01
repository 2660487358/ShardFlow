package com.shardflow.strategy.repository;

import com.baomidou.mybatisplus.core.mapper.BaseMapper;
import com.shardflow.common.entity.StrategyEntity;
import org.apache.ibatis.annotations.Mapper;

@Mapper
public interface StrategyRepository extends BaseMapper<StrategyEntity> {
}
