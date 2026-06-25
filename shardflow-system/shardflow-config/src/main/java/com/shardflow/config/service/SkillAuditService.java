package com.shardflow.config.service;

import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import tools.jackson.core.JacksonException;
import tools.jackson.databind.ObjectMapper;
import com.shardflow.config.entity.SkillAuditLogEntity;
import com.shardflow.config.repository.SkillAuditLogRepository;
import com.shardflow.usercontext.context.UserContext;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.scheduling.annotation.Async;
import org.springframework.stereotype.Service;

import java.time.Instant;
import java.util.List;
import java.util.Map;

/**
 * Skill 审计日志服务.
 *
 * <p>Per Skills管理需求规格文档 FR-8.7 / FR-8.8 / IR-8 / 实施计划 P6.4.
 * <p>记录所有 Skill 操作与执行调用：
 * <ul>
 *   <li>CRUD 操作（CREATE/UPDATE/DELETE/STATUS_CHANGE）</li>
 *   <li>版本管理（PUBLISH/ROLLBACK）</li>
 *   <li>权限变更（PERMISSION_CHANGE）</li>
 *   <li>执行调用（EXECUTE/SKILL_LOAD）</li>
 *   <li>准入扫描（ADMISSION_SCAN/ADMISSION_REVIEW/SANDBOX_TEST）</li>
 *   <li>导入导出（IMPORT/EXPORT）</li>
 * </ul>
 *
 * <p>支持按 Skill 查询审计日志，记录调用性能指标（latency_ms / tokens_used）。
 */
@Slf4j
@Service
@RequiredArgsConstructor
public class SkillAuditService {

    private final SkillAuditLogRepository auditLogRepository;
    private final ObjectMapper objectMapper;

    /**
     * 记录审计日志（异步）.
     *
     * @param skillId    Skill ID
     * @param skillCode  Skill 编码
     * @param operation  操作类型
     * @param operatorId 操作者ID
     * @param details    操作详情（Map，将被序列化为 JSON 写入 JSONB 列）
     * @param latencyMs  调用延迟（毫秒）
     * @param tokensUsed Token 消耗
     * @param success    是否成功
     * @param error      错误信息
     */
    @Async
    public void recordAudit(
            Long skillId,
            String skillCode,
            String operation,
            String operatorId,
            Map<String, Object> details,
            int latencyMs,
            int tokensUsed,
            boolean success,
            String error
    ) {
        try {
            SkillAuditLogEntity entity = new SkillAuditLogEntity();
            entity.setSkillId(skillId);
            entity.setOperation(operation);
            entity.setOperatorId(operatorId != null ? operatorId : "system");
            entity.setOperatorType("user");
            entity.setDetails(objectMapper.writeValueAsString(details));
            entity.setLatencyMs(latencyMs);
            entity.setTokensUsed(tokensUsed);
            entity.setSuccess(success);
            entity.setError(error);
            entity.setCreatedAt(Instant.now());

            auditLogRepository.insert(entity);
            log.debug("SkillAuditService: recorded skill={} operation={} success={}",
                    skillCode, operation, success);
        } catch (JacksonException e) {
            log.warn("SkillAuditService: failed to serialize audit details to JSON skill={} operation={} error={}",
                    skillCode, operation, e.getMessage());
        } catch (Exception e) {
            log.warn("SkillAuditService: failed to record audit log skill={} operation={} error={}",
                    skillCode, operation, e.getMessage());
        }
    }

    /**
     * 记录审计日志（带会话信息，用于执行调用）.
     */
    @Async
    public void recordExecutionAudit(
            Long skillId,
            String skillCode,
            String agentId,
            String sessionId,
            String operation,
            String operatorId,
            Map<String, Object> details,
            int latencyMs,
            int tokensUsed,
            boolean success,
            String error
    ) {
        try {
            SkillAuditLogEntity entity = new SkillAuditLogEntity();
            entity.setSkillId(skillId);
            entity.setAgentId(agentId);
            entity.setSessionId(sessionId);
            entity.setOperation(operation);
            entity.setOperatorId(operatorId != null ? operatorId : "system");
            entity.setOperatorType("user");
            entity.setDetails(objectMapper.writeValueAsString(details));
            entity.setLatencyMs(latencyMs);
            entity.setTokensUsed(tokensUsed);
            entity.setSuccess(success);
            entity.setError(error);
            entity.setCreatedAt(Instant.now());

            auditLogRepository.insert(entity);
        } catch (JacksonException e) {
            log.warn("SkillAuditService: failed to serialize execution audit details to JSON skill={} error={}",
                    skillCode, e.getMessage());
        } catch (Exception e) {
            log.warn("SkillAuditService: failed to record execution audit skill={} error={}",
                    skillCode, e.getMessage());
        }
    }

    /**
     * 查询 Skill 审计日志.
     *
     * @param skillId Skill ID
     * @param limit   返回条数上限
     * @return 审计日志列表
     */
    public List<SkillAuditLogEntity> listAuditLogs(Long skillId, int limit) {
        LambdaQueryWrapper<SkillAuditLogEntity> wrapper = new LambdaQueryWrapper<>();
        wrapper.eq(SkillAuditLogEntity::getSkillId, skillId)
                .orderByDesc(SkillAuditLogEntity::getCreatedAt)
                .last("LIMIT " + Math.min(Math.max(limit, 1), 500));
        return auditLogRepository.selectList(wrapper);
    }

    /**
     * 查询 Skill 审计日志（按时间范围）.
     */
    public List<SkillAuditLogEntity> listAuditLogsByTimeRange(
            Long skillId, Instant startTime, Instant endTime
    ) {
        LambdaQueryWrapper<SkillAuditLogEntity> wrapper = new LambdaQueryWrapper<>();
        wrapper.eq(SkillAuditLogEntity::getSkillId, skillId)
                .ge(SkillAuditLogEntity::getCreatedAt, startTime)
                .le(SkillAuditLogEntity::getCreatedAt, endTime)
                .orderByDesc(SkillAuditLogEntity::getCreatedAt);
        return auditLogRepository.selectList(wrapper);
    }
}
