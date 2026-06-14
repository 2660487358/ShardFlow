package com.shardflow.strategy.repository;

import com.baomidou.mybatisplus.core.mapper.BaseMapper;
import com.shardflow.common.entity.StrategyRecordEntity;
import org.apache.ibatis.annotations.Mapper;

@Mapper
public interface StrategyRecordRepository extends BaseMapper<StrategyRecordEntity> {
}
