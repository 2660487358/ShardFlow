package com.shardflow.profile.repository;

import com.baomidou.mybatisplus.core.mapper.BaseMapper;
import com.shardflow.common.entity.UserProfileEntity;
import org.apache.ibatis.annotations.Mapper;

@Mapper
public interface UserProfileRepository extends BaseMapper<UserProfileEntity> {
}
