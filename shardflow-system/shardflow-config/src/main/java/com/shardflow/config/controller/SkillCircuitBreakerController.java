package com.shardflow.config.controller;

import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import com.shardflow.common.dto.Result;
import com.shardflow.config.entity.SkillRegistryEntity;
import com.shardflow.config.repository.SkillRegistryRepository;
import com.shardflow.config.support.SkillCircuitBreaker;
import com.shardflow.config.support.SkillCircuitBreaker.BreakerStatus;
import com.shardflow.config.support.SkillPermissionChecker;
import com.shardflow.usercontext.context.UserContext;
import lombok.RequiredArgsConstructor;
import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.*;
import org.springframework.web.server.ResponseStatusException;

/**
 * Skill 熔断器管理 REST API.
 *
 * <p>Per Skills管理需求规格文档 FR-8.5 / 实施计划 P6.3.
 * <p>提供 Skill 级熔断器的状态查询与手动重置接口.
 *
 * <p>接口清单：
 * <ul>
 *   <li>GET  /api/v1/skills/{skill_code}/circuit-breaker  — 查询熔断器状态（需读权限）</li>
 *   <li>POST /api/v1/skills/{skill_code}/circuit-breaker/reset — 手动重置熔断器（需管理权限）</li>
 * </ul>
 *
 * <p>安全要求：
 * <ul>
 *   <li>查询状态：需通过 SkillPermissionChecker.checkReadPermission 校验</li>
 *   <li>手动重置：需通过 SkillPermissionChecker.checkManagePermission 校验（仅 owner/admin）</li>
 * </ul>
 */
@RestController
@RequestMapping("/api/v1/skills/{skill_code}/circuit-breaker")
@RequiredArgsConstructor
public class SkillCircuitBreakerController {

    private final SkillCircuitBreaker circuitBreaker;
    private final SkillRegistryRepository skillRegistryRepository;
    private final SkillPermissionChecker permissionChecker;

    // ── 查询熔断器状态（需读权限）──

    @GetMapping
    public Result<BreakerStatus> getStatus(
            @PathVariable("skill_code") String skillCode) {
        String userId = UserContext.getUserId();
        SkillRegistryEntity skill = findSkill(skillCode);
        permissionChecker.checkReadPermission(userId, skill);
        return Result.ok(circuitBreaker.getStatus(skillCode));
    }

    // ── 手动重置熔断器（需管理权限）──

    @PostMapping("/reset")
    @ResponseStatus(HttpStatus.OK)
    public Result<Void> reset(
            @PathVariable("skill_code") String skillCode) {
        String userId = UserContext.getUserId();
        SkillRegistryEntity skill = findSkill(skillCode);
        permissionChecker.checkManagePermission(userId, skill);
        circuitBreaker.reset(skillCode);
        return Result.ok();
    }

    // ── 辅助方法 ──

    private SkillRegistryEntity findSkill(String skillCode) {
        SkillRegistryEntity skill = skillRegistryRepository.selectOne(
                new LambdaQueryWrapper<SkillRegistryEntity>()
                        .eq(SkillRegistryEntity::getSkillCode, skillCode)
        );
        if (skill == null) {
            throw new ResponseStatusException(HttpStatus.NOT_FOUND,
                    "Skill not found: " + skillCode);
        }
        return skill;
    }
}
