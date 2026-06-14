package com.shardflow.memory.repository;

import com.baomidou.mybatisplus.core.mapper.BaseMapper;
import com.shardflow.common.entity.MemoryChunkEntity;
import org.apache.ibatis.annotations.Mapper;

@Mapper
public interface MemoryChunkRepository extends BaseMapper<MemoryChunkEntity> {
}
