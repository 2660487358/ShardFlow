package com.shardflow.profile.repository;

import com.baomidou.mybatisplus.core.mapper.BaseMapper;
import com.shardflow.common.entity.ProfileEntity;
import org.apache.ibatis.annotations.Mapper;

@Mapper
public interface ProfileRepository extends BaseMapper<ProfileEntity> {
}
