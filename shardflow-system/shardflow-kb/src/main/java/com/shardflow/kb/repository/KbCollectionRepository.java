package com.shardflow.kb.repository;

import com.baomidou.mybatisplus.core.mapper.BaseMapper;
import com.shardflow.common.entity.KbCollectionEntity;
import org.apache.ibatis.annotations.Mapper;

@Mapper
public interface KbCollectionRepository extends BaseMapper<KbCollectionEntity> {
}
