package com.shardflow.config.service;

import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import com.shardflow.config.dto.CostAnalysisDTO;
import com.shardflow.config.entity.SkillAuditLogEntity;
import com.shardflow.config.entity.SkillRegistryEntity;
import com.shardflow.config.repository.SkillAuditLogRepository;
import com.shardflow.config.repository.SkillRegistryRepository;
import com.shardflow.usercontext.context.UserContext;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Service;
import org.springframework.web.server.ResponseStatusException;

import java.time.Instant;
import java.time.temporal.ChronoUnit;
import java.util.ArrayList;
import java.util.List;

/**
 * Skill 成本分析服务.
 *
 * <p>Per Skills管理需求规格文档 FR-8.8 / IR-8 / 实施计划 P6.5.
 * <p>按 Skill 统计 Token 消耗、调用次数、平均延迟、总成本，支持 30 天内查询.
 *
 * <p>数据来源：skill_audit_log 表中 operation='EXECUTE' 或 'SKILL_LOAD' 的记录.
 */
@Slf4j
@Service
@RequiredArgsConstructor
public class SkillCostAnalysisService {

    private final SkillAuditLogRepository auditLogRepository;
    private final SkillRegistryRepository skillRegistryRepository;

    /**
     * 查询单个 Skill 的成本分析（默认 30 天）.
     *
     * @param skillCode Skill 编码
     * @return 成本分析结果
     */
    public CostAnalysisDTO analyzeSkillCost(String skillCode) {
        return analyzeSkillCost(skillCode, 30);
    }

    /**
     * 查询单个 Skill 的成本分析.
     *
     * @param skillCode  Skill 编码
     * @param daysBack   查询天数（1~90）
     * @return 成本分析结果
     */
    public CostAnalysisDTO analyzeSkillCost(String skillCode, int daysBack) {
        String userId = UserContext.getUserId();
        SkillRegistryEntity skill = findSkill(skillCode);

        // 校验审计权限
        if (!userId.equals(skill.getOwnerId()) && !userId.equals(skill.getUserId())) {
            // 非 owner 用户需要 AUDIT 权限（V1 简化：仅 owner 或 skill:admin 可查询成本）
            List<String> permissions = UserContext.getPermissions();
            if (permissions == null || !permissions.contains("skill:admin")) {
                throw new ResponseStatusException(HttpStatus.FORBIDDEN,
                        "No permission to analyze cost for skill: " + skillCode);
            }
        }

        int days = Math.min(Math.max(daysBack, 1), 90);
        Instant startTime = Instant.now().minus(days, ChronoUnit.DAYS);

        List<SkillAuditLogEntity> logs = auditLogRepository.selectList(
                new LambdaQueryWrapper<SkillAuditLogEntity>()
                        .eq(SkillAuditLogEntity::getSkillId, skill.getId())
                        .in(SkillAuditLogEntity::getOperation, "EXECUTE", "SKILL_LOAD")
                        .ge(SkillAuditLogEntity::getCreatedAt, startTime)
        );

        return aggregateCost(skill, logs);
    }

    /**
     * 查询当前用户所有 Skill 的成本分析（默认 30 天）.
     *
     * @return 成本分析列表
     */
    public List<CostAnalysisDTO> analyzeUserSkillsCost() {
        return analyzeUserSkillsCost(30);
    }

    /**
     * 查询当前用户所有 Skill 的成本分析.
     *
     * @param daysBack 查询天数（1~90）
     * @return 成本分析列表
     */
    public List<CostAnalysisDTO> analyzeUserSkillsCost(int daysBack) {
        String userId = UserContext.getUserId();
        int days = Math.min(Math.max(daysBack, 1), 90);
        Instant startTime = Instant.now().minus(days, ChronoUnit.DAYS);

        // 查询用户的所有 Skill
        List<SkillRegistryEntity> skills = skillRegistryRepository.selectList(
                new LambdaQueryWrapper<SkillRegistryEntity>()
                        .eq(SkillRegistryEntity::getUserId, userId)
        );

        List<CostAnalysisDTO> results = new ArrayList<>();
        for (SkillRegistryEntity skill : skills) {
            List<SkillAuditLogEntity> logs = auditLogRepository.selectList(
                    new LambdaQueryWrapper<SkillAuditLogEntity>()
                            .eq(SkillAuditLogEntity::getSkillId, skill.getId())
                            .in(SkillAuditLogEntity::getOperation, "EXECUTE", "SKILL_LOAD")
                            .ge(SkillAuditLogEntity::getCreatedAt, startTime)
            );
            results.add(aggregateCost(skill, logs));
        }

        return results;
    }

    // ── 内部方法 ──

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

    /**
     * 聚合审计日志为成本分析 DTO.
     */
    private CostAnalysisDTO aggregateCost(SkillRegistryEntity skill, List<SkillAuditLogEntity> logs) {
        CostAnalysisDTO dto = new CostAnalysisDTO();
        dto.setSkillId(skill.getId());
        dto.setSkillCode(skill.getSkillCode());
        dto.setSkillName(skill.getSkillName());

        long callCount = logs.size();
        long successCount = logs.stream().filter(l -> Boolean.TRUE.equals(l.getSuccess())).count();
        long failureCount = callCount - successCount;

        long totalTokens = logs.stream()
                .mapToLong(l -> l.getTokensUsed() != null ? l.getTokensUsed() : 0)
                .sum();

        // V1 简化：input/output tokens 按 3:7 比例拆分（实际应从 details JSON 解析）
        long inputTokens = (long) (totalTokens * 0.3);
        long outputTokens = totalTokens - inputTokens;

        long avgLatency = (long) logs.stream()
                .mapToInt(l -> l.getLatencyMs() != null ? l.getLatencyMs() : 0)
                .filter(v -> v > 0)
                .average()
                .orElse(0.0);

        long maxLatency = logs.stream()
                .mapToInt(l -> l.getLatencyMs() != null ? l.getLatencyMs() : 0)
                .max()
                .orElse(0);

        // V1 简化：成本估算 = tokens * 0.0001（实际应从 skill.cost_estimate 解析单价）
        java.math.BigDecimal totalCost = java.math.BigDecimal.valueOf(totalTokens)
                .multiply(java.math.BigDecimal.valueOf(0.0001));

        dto.setCallCount(callCount);
        dto.setSuccessCount(successCount);
        dto.setFailureCount(failureCount);
        dto.setTotalInputTokens(inputTokens);
        dto.setTotalOutputTokens(outputTokens);
        dto.setAvgLatencyMs(avgLatency);
        dto.setMaxLatencyMs(maxLatency);
        dto.setTotalCost(totalCost);

        return dto;
    }
}
