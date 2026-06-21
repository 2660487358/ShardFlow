package com.shardflow.profile.repository;

import com.baomidou.mybatisplus.core.mapper.BaseMapper;
import com.shardflow.common.entity.UserProfileHistoryEntity;
import org.apache.ibatis.annotations.Mapper;

@Mapper
public interface UserProfileHistoryRepository extends BaseMapper<UserProfileHistoryEntity> {
}
