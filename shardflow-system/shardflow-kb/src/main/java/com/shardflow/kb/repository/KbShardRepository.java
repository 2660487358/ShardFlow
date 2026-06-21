package com.shardflow.kb.repository;

import com.baomidou.mybatisplus.core.mapper.BaseMapper;
import com.shardflow.common.entity.KbShardEntity;
import org.apache.ibatis.annotations.Mapper;

@Mapper
public interface KbShardRepository extends BaseMapper<KbShardEntity> {
}
