package com.shardflow.config.controller;

import com.shardflow.common.dto.Result;
import com.shardflow.config.dto.CostAnalysisDTO;
import com.shardflow.config.dto.SkillAuditLogDTO;
import com.shardflow.config.entity.SkillAuditLogEntity;
import com.shardflow.config.entity.SkillRegistryEntity;
import com.shardflow.config.repository.SkillRegistryRepository;
import com.shardflow.config.service.SkillAuditService;
import com.shardflow.config.service.SkillCostAnalysisService;
import com.shardflow.config.support.SkillPermissionChecker;
import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import com.shardflow.config.repository.SkillAuditLogRepository;
import com.shardflow.usercontext.context.UserContext;
import lombok.RequiredArgsConstructor;
import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.*;
import org.springframework.web.server.ResponseStatusException;

import java.time.Instant;
import java.time.temporal.ChronoUnit;
import java.util.List;
import java.util.stream.Collectors;

/**
 * Skill 审计日志管理 REST API.
 *
 * <p>Per Skills管理需求规格文档 FR-8.7 / FR-8.8 / IR-8 / 实施计划 P6.4.
 * <p>提供审计日志查询与成本分析接口.
 *
 * <p>接口清单：
 * <ul>
 *   <li>GET /api/v1/skills/{skill_code}/audit-logs  — 查询 Skill 审计日志（P6.4.2）</li>
 *   <li>GET /api/v1/skills/{skill_code}/cost-analysis — 查询 Skill 成本分析（P6.4.3）</li>
 *   <li>GET /api/v1/skills/cost-analysis — 查询当前用户所有 Skill 成本分析（P6.5）</li>
 * </ul>
 */
@RestController
@RequiredArgsConstructor
public class SkillAuditController {

    private final SkillAuditService auditService;
    private final SkillCostAnalysisService costAnalysisService;
    private final SkillAuditLogRepository auditLogRepository;
    private final SkillRegistryRepository skillRegistryRepository;
    private final SkillPermissionChecker permissionChecker;

    // ── P6.4.2 查询 Skill 审计日志 ──

    @GetMapping("/api/v1/skills/{skill_code}/audit-logs")
    public Result<List<SkillAuditLogDTO>> listAuditLogs(
            @PathVariable("skill_code") String skillCode,
            @RequestParam(value = "limit", defaultValue = "100") int limit,
            @RequestParam(value = "days_back", defaultValue = "30") int daysBack) {

        String userId = UserContext.getUserId();
        SkillRegistryEntity skill = findSkill(skillCode);

        // 校验审计权限
        permissionChecker.checkAuditPermission(userId, skill);

        int days = Math.min(Math.max(daysBack, 1), 90);
        Instant startTime = Instant.now().minus(days, ChronoUnit.DAYS);

        LambdaQueryWrapper<SkillAuditLogEntity> wrapper = new LambdaQueryWrapper<SkillAuditLogEntity>()
                .eq(SkillAuditLogEntity::getSkillId, skill.getId())
                .ge(SkillAuditLogEntity::getCreatedAt, startTime)
                .orderByDesc(SkillAuditLogEntity::getCreatedAt)
                .last("LIMIT " + Math.min(Math.max(limit, 1), 500));

        List<SkillAuditLogEntity> logs = auditLogRepository.selectList(wrapper);

        List<SkillAuditLogDTO> dtos = logs.stream()
                .map(this::toDTO)
                .collect(Collectors.toList());

        return Result.ok(dtos);
    }

    // ── P6.4.3 查询单个 Skill 成本分析 ──

    @GetMapping("/api/v1/skills/{skill_code}/cost-analysis")
    public Result<CostAnalysisDTO> getSkillCostAnalysis(
            @PathVariable("skill_code") String skillCode,
            @RequestParam(value = "days_back", defaultValue = "30") int daysBack) {
        return Result.ok(costAnalysisService.analyzeSkillCost(skillCode, daysBack));
    }

    // ── P6.5 查询当前用户所有 Skill 成本分析 ──

    @GetMapping("/api/v1/skills/cost-analysis")
    public Result<List<CostAnalysisDTO>> getUserSkillsCostAnalysis(
            @RequestParam(value = "days_back", defaultValue = "30") int daysBack) {
        return Result.ok(costAnalysisService.analyzeUserSkillsCost(daysBack));
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

    private SkillAuditLogDTO toDTO(SkillAuditLogEntity entity) {
        SkillAuditLogDTO dto = new SkillAuditLogDTO();
        dto.setId(entity.getId());
        dto.setSkillId(entity.getSkillId());
        dto.setAgentId(entity.getAgentId());
        dto.setOperation(entity.getOperation());
        dto.setOperatorId(entity.getOperatorId());
        dto.setOperatorType(entity.getOperatorType());
        dto.setRequestId(entity.getRequestId());
        dto.setIpAddress(entity.getIpAddress());
        dto.setUserAgent(entity.getUserAgent());
        dto.setCreatedAt(entity.getCreatedAt());
        // details 字段为 JSON 字符串，V1 简化：不解析为 Map，保持 null
        return dto;
    }
}
