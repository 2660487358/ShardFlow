package com.shardflow.config.repository;

import com.baomidou.mybatisplus.core.mapper.BaseMapper;
import com.shardflow.config.entity.SkillPermissionEntity;
import org.apache.ibatis.annotations.Mapper;

/**
 * Skill 权限配置 Mapper.
 *
 * <p>Per Skills管理需求规格文档 DR-1 / 实施计划 P2.2.
 */
@Mapper
public interface SkillPermissionRepository extends BaseMapper<SkillPermissionEntity> {
}
