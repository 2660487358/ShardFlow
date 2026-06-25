package com.shardflow.config.service;

import com.shardflow.config.dto.CreateSkillRequest;
import com.shardflow.config.dto.SkillDTO;
import com.shardflow.config.dto.SkillDetailDTO;
import com.shardflow.config.dto.SkillStatusRequest;
import com.shardflow.config.dto.UpdateSkillRequest;
import com.shardflow.config.dto.SkillQueryRequest;

import java.util.Map;

/**
 * Skill 生命周期管理服务接口.
 *
 * <p>Per Skills管理需求规格文档 FR-1 / FR-4 / 实施计划 P2.2~P2.4.
 * <p>提供 Skill 的 CRUD、状态切换、分类搜索、基础权限控制。
 */
public interface SkillService {

    /**
     * 创建 Skill.
     * FR-1.1 / P2.2.1: POST /api/v1/skills
     *
     * @param request 创建请求
     * @return 创建的 Skill DTO
     */
    SkillDTO createSkill(CreateSkillRequest request);

    /**
     * 分页列表查询.
     * FR-4 / P2.2.2: GET /api/v1/skills
     *
     * @param query 查询条件（分页+筛选）
     * @return 包含 skills/total/page/size 的 Map
     */
    Map<String, Object> listSkills(SkillQueryRequest query);

    /**
     * 查询 Skill 详情.
     * FR-1.3 / P2.2.3: GET /api/v1/skills/{skill_code}
     *
     * @param skillCode Skill 编码
     * @return Skill 详情 DTO（含关联 Agent 和版本历史）
     */
    SkillDetailDTO getSkillDetail(String skillCode);

    /**
     * 更新 Skill.
     * FR-1.4 / P2.2.4: PUT /api/v1/skills/{skill_code}
     *
     * @param skillCode Skill 编码
     * @param request   更新请求
     * @return 更新后的 Skill DTO
     */
    SkillDTO updateSkill(String skillCode, UpdateSkillRequest request);

    /**
     * 删除 Skill（级联删除关联记录）.
     * FR-1.5 / P2.2.5: DELETE /api/v1/skills/{skill_code}
     *
     * @param skillCode Skill 编码
     */
    void deleteSkill(String skillCode);

    /**
     * 状态切换.
     * FR-1.6 / P2.2.6: PATCH /api/v1/skills/{skill_code}/status
     *
     * @param skillCode Skill 编码
     * @param request   状态切换请求
     * @return 更新后的 Skill DTO
     */
    SkillDTO changeStatus(String skillCode, SkillStatusRequest request);
}
