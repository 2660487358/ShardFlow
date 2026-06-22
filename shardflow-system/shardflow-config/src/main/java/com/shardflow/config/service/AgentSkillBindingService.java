package com.shardflow.config.service;

import com.shardflow.config.dto.AgentSkillBindingRequest;
import com.shardflow.config.dto.SkillDetailDTO;

import java.util.List;

/**
 * Agent-Skill 绑定服务接口.
 *
 * <p>Per Skills管理需求规格文档 FR-5 / 实施计划 P4.1.
 */
public interface AgentSkillBindingService {

    /**
     * 批量更新 Agent 的 Skill 绑定关系（全量替换）.
     * FR-5.5 / P4.1.1: POST /api/v1/agents/{agent_id}/skills
     *
     * @param agentId  Agent 编码（agent_code）
     * @param request  绑定请求
     */
    void updateAgentSkills(String agentId, AgentSkillBindingRequest request);

    /**
     * 查询 Agent 当前绑定的 Skill 列表.
     *
     * @param agentId Agent 编码
     * @return 绑定列表
     */
    List<AgentSkillBindingRequest.BindingItem> listAgentSkills(String agentId);

    /**
     * 删除 Agent 的所有 Skill 绑定.
     * NFR-2.4 / P4.1.7: Agent 删除时级联解绑
     *
     * @param agentId Agent 编码
     */
    void deleteByAgentId(String agentId);

    /**
     * 查询 Skill 关联的 Agent 列表.
     * FR-5.7 / P4.1.5: GET /api/v1/skills/{skill_code}/agents
     *
     * @param skillCode Skill 编码
     * @return Agent 关联摘要列表
     */
    List<SkillDetailDTO.AgentRef> listSkillAgents(String skillCode);
}
