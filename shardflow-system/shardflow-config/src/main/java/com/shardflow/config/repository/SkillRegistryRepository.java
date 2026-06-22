package com.shardflow.config.repository;

import com.baomidou.mybatisplus.core.mapper.BaseMapper;
import com.shardflow.config.entity.SkillRegistryEntity;
import org.apache.ibatis.annotations.Mapper;

/**
 * Skill 注册表 Mapper.
 *
 * <p>Per Skills管理需求规格文档 DR-1 / 实施计划 P2.2.
 * <p>MyBatis-Plus BaseMapper 提供 insert/selectById/selectPage/selectList/selectCount/updateById/delete 等基础方法。
 */
@Mapper
public interface SkillRegistryRepository extends BaseMapper<SkillRegistryEntity> {
}
