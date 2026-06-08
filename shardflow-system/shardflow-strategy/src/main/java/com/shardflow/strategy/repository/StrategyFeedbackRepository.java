package com.shardflow.strategy.repository;

import com.baomidou.mybatisplus.core.mapper.BaseMapper;
import com.shardflow.common.entity.StrategyFeedbackEntity;
import org.apache.ibatis.annotations.Mapper;

@Mapper
public interface StrategyFeedbackRepository extends BaseMapper<StrategyFeedbackEntity> {
}
