package com.shardflow.config.controller;

import com.shardflow.common.dto.Result;
import com.shardflow.config.dto.AgentSkillBindingRequest;
import com.shardflow.config.service.AgentSkillBindingService;
import jakarta.validation.Valid;
import lombok.RequiredArgsConstructor;
import org.springframework.web.bind.annotation.*;

import java.util.List;

/**
 * Agent-Skill 绑定关系 REST API.
 *
 * <p>Per Skills管理需求规格文档 FR-5 / 实施计划 P4.1.
 * <p>提供 Agent 与 Skill 的批量绑定更新、当前绑定查询接口。
 *
 * <p>接口清单：
 * <ul>
 *   <li>POST /api/v1/agents/{agent_id}/skills — 批量更新绑定（P4.1.1）</li>
 *   <li>GET  /api/v1/agents/{agent_id}/skills — 查询当前绑定（P4.1 辅助）</li>
 * </ul>
 */
@RestController
@RequestMapping("/api/v1/agents/{agent_id}")
@RequiredArgsConstructor
public class AgentSkillBindingController {

    private final AgentSkillBindingService bindingService;

    // ── P4.1.1 批量更新 Agent-Skill 绑定（全量替换）──

    @PostMapping("/skills")
    public Result<Void> bindSkills(
            @PathVariable("agent_id") String agentId,
            @Valid @RequestBody AgentSkillBindingRequest request) {
        bindingService.updateAgentSkills(agentId, request);
        return Result.ok();
    }

    // ── 查询 Agent 当前绑定的 Skill 列表 ──

    @GetMapping("/skills")
    public Result<List<AgentSkillBindingRequest.BindingItem>> listAgentSkills(
            @PathVariable("agent_id") String agentId) {
        return Result.ok(bindingService.listAgentSkills(agentId));
    }
}
