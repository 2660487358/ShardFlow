package com.shardflow.task.repository;

import com.baomidou.mybatisplus.core.mapper.BaseMapper;
import com.shardflow.common.entity.TaskSessionEntity;
import org.apache.ibatis.annotations.Mapper;

@Mapper
public interface TaskSessionRepository extends BaseMapper<TaskSessionEntity> {
}
