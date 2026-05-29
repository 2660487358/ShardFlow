package com.shardflow.strategy.repository;

import com.baomidou.mybatisplus.core.mapper.BaseMapper;
import com.shardflow.common.entity.StrategyEntity;
import org.apache.ibatis.annotations.Mapper;
import org.apache.ibatis.annotations.Param;
import org.apache.ibatis.annotations.Select;

import java.util.List;

@Mapper
public interface StrategyRepository extends BaseMapper<StrategyEntity> {

    @Select("SELECT *, 1 - (embedding <=> CAST(#{queryVector} AS vector)) AS similarity " +
            "FROM shardflow_strategy " +
            "WHERE embedding IS NOT NULL " +
            "ORDER BY embedding <=> CAST(#{queryVector} AS vector) " +
            "LIMIT #{limit}")
    List<Object[]> searchSimilar(@Param("queryVector") String queryVector,
                                 @Param("limit") int limit);
}
