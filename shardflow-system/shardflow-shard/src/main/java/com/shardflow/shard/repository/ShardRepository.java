package com.shardflow.shard.repository;

import com.baomidou.mybatisplus.core.mapper.BaseMapper;
import com.shardflow.common.entity.ShardEntity;
import org.apache.ibatis.annotations.Mapper;

@Mapper
public interface ShardRepository extends BaseMapper<ShardEntity> {
}
