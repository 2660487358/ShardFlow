package com.shardflow.kb.repository;

import com.baomidou.mybatisplus.core.mapper.BaseMapper;
import com.shardflow.common.entity.KbDocumentEntity;
import org.apache.ibatis.annotations.Mapper;

@Mapper
public interface KbDocumentRepository extends BaseMapper<KbDocumentEntity> {
}
