package com.shardflow.shard.repository;

import com.baomidou.mybatisplus.core.mapper.BaseMapper;
import com.shardflow.common.entity.SessionStateSummaryEntity;
import org.apache.ibatis.annotations.Mapper;

@Mapper
public interface SessionStateSummaryRepository extends BaseMapper<SessionStateSummaryEntity> {
}
