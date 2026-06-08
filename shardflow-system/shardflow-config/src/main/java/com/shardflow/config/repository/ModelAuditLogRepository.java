package com.shardflow.config.repository;

import com.baomidou.mybatisplus.core.mapper.BaseMapper;
import com.shardflow.common.entity.ModelAuditLogEntity;
import org.apache.ibatis.annotations.Mapper;

@Mapper
public interface ModelAuditLogRepository extends BaseMapper<ModelAuditLogEntity> {
}
